import os
import stat
import signal
import subprocess
import time
import random
import string
import psutil

from testing.common.database import (
    Database, DatabaseFactory, get_unused_port
)

__all__ = ['RabbitMQServer', 'RabbitMQServerFactory']

SEARCH_PATHS = [
    '/usr/lib/rabbitmq/bin',  # archlinux
    '/usr/local/opt/rabbitmq/sbin'  # macOS homebrew
]

# https://www.rabbitmq.com/configure.html#customise-environment
SCRIPT_SOURCE = """#!/usr/bin/env bash
export RABBITMQ_NODENAME={2}
export RABBITMQ_NODE_IP_ADDRESS=127.0.0.1
export RABBITMQ_NODE_PORT={3}
export RABBITMQ_DIST_PORT={4}
export RABBITMQ_CONFIG_FILE={0}/rabbit.conf
export RABBITMQ_MNESIA_BASE={0}/mnesia
export RABBITMQ_LOG_BASE={0}/log
export RABBITMQ_SCHEMA_DIR={0}/schema
export RABBITMQ_GENERATED_CONFIG_DIR={0}/config
export RABBITMQ_ADVANCED_CONFIG_FILE={0}/rabbit-advanced.config
export RABBITMQ_ENABLED_PLUGINS_FILE={0}/rabbit-plugins.conf
export RABBITMQ_SERVER_START_ARGS="-mnesia core_dir false"
export HOME={0}
SCRIPT_NAME=$1
shift
exec {1}/$SCRIPT_NAME "$@"
"""


class RabbitMQServer(Database):

    DEFAULT_SETTINGS = dict(auto_start=2,
                            base_dir=None,
                            copy_data_from=None,
                            node_name=None,
                            port=None,
                            dist_port=None,
                            rabbitmq_script_dir=None)

    subdirectories = ['data', 'tmp']

    def initialize(self):
        self.rabbitmq_script_dir = self.settings.get('rabbitmq_script_dir')
        if self.rabbitmq_script_dir is None:
            for path in SEARCH_PATHS:
                if os.path.exists(os.path.join(path, 'rabbitmq-server')):
                    self.rabbitmq_script_dir = path
                    break
            else:
                raise Exception("Unable to automatically find the location of 'rabbitmq-server'."
                                "Please set `rabbitmq_script_dir` manually")
        if not os.path.exists(os.path.join(self.rabbitmq_script_dir, 'rabbitmq-server')):
            raise Exception("Unable to find 'rabbitmq-server' in '{}'".format(self.rabbitmq_script_dir))
        if not os.path.exists(os.path.join(self.rabbitmq_script_dir, 'rabbitmqctl')):
            raise Exception("Unable to find 'rabbitmqctl' in '{}'".format(self.rabbitmq_script_dir))
        self.node_name = self.settings.get('node_name') or \
            ''.join(random.choices(string.ascii_lowercase, k=16))
        self._start_attempts = 0

    def dsn(self):
        return {
            "host": "localhost",
            "port": self.settings["port"]
        }

    def url(self):
        return "ampq://localhost:{}/".format(self.settings['port'])

    def get_data_directory(self):
        return os.path.join(self.base_dir, 'data')

    def prestart(self):
        super(RabbitMQServer, self).prestart()

        if self.settings["dist_port"] is None:
            self.settings["dist_port"] = get_unused_port()

        runner = os.path.join(self.base_dir, 'runner')
        with open(runner, 'w') as f:
            f.write(SCRIPT_SOURCE.format(
                self.base_dir,
                self.rabbitmq_script_dir,
                self.node_name,
                self.settings["port"],
                self.settings["dist_port"]
            ))
        st = os.stat(runner)
        os.chmod(runner, st.st_mode | stat.S_IEXEC)

        cookie_path = os.path.join(self.base_dir, '.erlang.cookie')
        if not os.path.exists(cookie_path):
            with open(cookie_path, 'w') as f:
                f.write(os.urandom(16).hex())
            os.chmod(cookie_path, stat.S_IRUSR)

    def get_server_commandline(self):
        runner = os.path.join(self.base_dir, 'runner')
        return [runner, 'rabbitmq-server']

    def is_server_available(self):
        try:
            p = psutil.Process(self.child_process.pid)
            has_port = False
            has_dist_port = False
            for c in p.children():
                for conn in c.connections(kind="all"):
                    if conn.laddr == ('127.0.0.1', self.settings["port"]):
                        has_port = True
                    if conn.laddr == ('0.0.0.0', self.settings["dist_port"]):
                        has_dist_port = True
                    if has_port and has_dist_port:
                        return True
            return False
        except psutil.AccessDenied:
            return False

    def rabbitmqctl_wait(self):
        rc = self._rabbitmqctl(
            'wait',
            os.path.join(self.base_dir, 'mnesia', '{}.pid'.format(self.node_name)))
        return rc == 0

    def terminate(self, _signal=signal.SIGTERM):
        if self.child_process is None or self.child_process.poll() is not None:
            return
        RabbitMQServer._terminate_process(self.child_process.pid)
        self.child_process.wait()
        self.child_process = None

    @staticmethod
    def _terminate_process(pid):
        """Tries hard to terminate and ultimately kill all the children of this process."""
        timeout = 10
        proc = psutil.Process(pid)
        procs = [proc] + proc.children(recursive=True)
        # send SIGTERM
        for p in procs:
            try:
                p.terminate()
            except psutil.NoSuchProcess:
                pass
        gone, alive = psutil.wait_procs(procs, timeout=timeout)
        if alive:
            # send SIGKILL
            for p in alive:
                print("process {} survived SIGTERM; trying SIGKILL" % p)
                try:
                    p.kill()
                except psutil.NoSuchProcess:
                    pass
            gone, alive = psutil.wait_procs(alive, timeout=timeout)
            if alive:
                # give up
                for p in alive:
                    print("process {} survived SIGKILL; giving up" % p)
                    raise RuntimeError("*** failed to shutdown child process ***")

    @staticmethod
    def _terminate_all():
        """Terminates all rabbitmq-server processes tied to the the core python process"""
        proc = psutil.Process()
        for p in proc.children():
            if p.name() == 'rabbitmq-server':
                RabbitMQServer._terminate_process(p.pid)
                p.wait()

    def _rabbitmqctl(self, cmd, *args, return_output=False):
        runner = os.path.join(self.base_dir, 'runner')
        p = subprocess.Popen(
            [runner, 'rabbitmqctl', cmd] + list(args),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        outs, errs = p.communicate(timeout=10)
        p.wait()
        if return_output:
            return p.returncode, outs.decode('utf-8'), errs.decode('utf-8')
        return p.returncode

    def reset(self):
        self._rabbitmqctl('stop_app')
        self._rabbitmqctl('force_reset')
        self._rabbitmqctl('start_app')
        while not self.is_server_available():
            time.sleep(0.1)

    def read_rabbitmq_logs(self):
        time.sleep(1)
        log_file = os.path.join(self.base_dir, 'log', '{}.log'.format(self.node_name))
        print(">>>>>>", log_file, "<<<<<<")
        with open(log_file) as f:
            return f.read()


class RabbitMQServerFactory(DatabaseFactory):
    target_class = RabbitMQServer

import unittest
import time
import functools
import os
import pika
import logging
import testing.rabbitmq

logging.getLogger("pika").propagate = False
LOG = logging.getLogger("tests")

def try_publish(rabbitmq):
    connection1 = pika.BlockingConnection(
        pika.ConnectionParameters(**rabbitmq.dsn()))
    connection2 = pika.BlockingConnection(
        pika.ConnectionParameters(**rabbitmq.dsn()))
    try:
        channel1 = connection1.channel()
        channel2 = connection2.channel()
        queue = channel2.queue_declare(queue='test')\
            .method.queue

        channel1.basic_publish(exchange='',
                               routing_key='test',
                               body=b'Test message.')

        def on_message(channel, method_frame, _header_frame, body):
            channel.basic_ack(method_frame.delivery_tag)
            channel.stop_consuming()
            assert body == b'Test message.'
        channel2.basic_consume(queue, on_message)
        channel2.start_consuming()
        return True
    except Exception:
        LOG.exception("Error publishing")
        return False
    finally:
        connection1.close()
        connection2.close()

class TestRabbitMQ(unittest.TestCase):

    def tearDown(self):
        testing.rabbitmq.RabbitMQServer._terminate_all()

    def test_basic(self):
        # start rabbitmq server
        rabbitmq = testing.rabbitmq.RabbitMQServer()
        self.assertIsNotNone(rabbitmq)

        pid = rabbitmq.server_pid
        self.assertTrue(rabbitmq.is_alive())

        self.assertTrue(try_publish(rabbitmq))

        rabbitmq.stop()
        time.sleep(1)

        self.assertFalse(rabbitmq.is_alive())
        with self.assertRaises(OSError):
            os.kill(pid, 0) # process is down

    def test_consecutive_runs(self):
        # NOTE: prints are for timing the start, stop and reset functions
        stime = time.time()
        with testing.rabbitmq.RabbitMQServer() as rmq:
            print("RUN1", time.time() - stime)
            stime = time.time()
        print("STOP1", time.time() - stime)
        stime = time.time()
        with testing.rabbitmq.RabbitMQServer() as rmq:
            print("RUN2", time.time() - stime)
            stime = time.time()
            rmq.reset()
            print("RESET", time.time() - stime)
            stime = time.time()
            self.assertTrue(try_publish(rmq))
        print("STOP2", time.time() - stime)

    def test_multiple_runs(self):
        rabbitmq1 = testing.rabbitmq.RabbitMQServer()
        rabbitmq2 = testing.rabbitmq.RabbitMQServer()

        self.assertIsNotNone(rabbitmq1)
        self.assertTrue(rabbitmq1.is_alive())
        self.assertIsNotNone(rabbitmq2)
        self.assertTrue(rabbitmq2.is_alive())

        self.assertTrue(try_publish(rabbitmq1))
        self.assertTrue(try_publish(rabbitmq2))

        rabbitmq1.stop()
        rabbitmq2.stop()

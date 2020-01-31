About
=====
``testing.rabbitmq`` automatically setups a rabbitmq instance, and destroys it after testing.

.. image:: https://travis-ci.org/tristan/testing.rabbitmq.svg?branch=master
   :target: https://travis-ci.org/tristan/testing.rabbitmq

.. image:: https://coveralls.io/repos/tristan/testing.rabbitmq/badge.png?branch=master
   :target: https://coveralls.io/r/tristan/testing.rabbitmq?branch=master

.. image:: https://codeclimate.com/github/tristan/testing.rabbitmq/badges/gpa.svg
   :target: https://codeclimate.com/github/tristan/testing.rabbitmq


Documentation
  https://github.com/tristan/testing.rabbitmq
Issues
  https://github.com/tristan/testing.rabbitmq/issues
Download
  https://pypi.python.org/pypi/testing.rabbitmq

Install
=======
Use pip::

   $ pip install testing.rabbitmq

And ``testing.rabbitmq`` requires ``rabbitmq-server`` and ``rabbitmqctl`` at ``/usr/lib/rabbitmq/bin``. If rabbitmq is installed at a different path set ``rabbitmq_script_dir`` when creating the ``RabbitMQServer`` instance.


Usage
=====
Create RabbitMQServer instance using ``testing.rabbitmq.RabbitMQServer``::

  import testing.rabbitmq
  import pika

  # Lanuch new RabbitMQ server
  with testing.rabbitmq.RabbitMQServer() as rmq:
      connection = pika.BlockingConnection(
          pika.ConnectionParameters(**rmq.dsn()))
      channel = connection.channel()
      channel.basic_publish(exchange='',
                            routing_key='test',
                            body=b'Test message.')
      connection.close()

  # Rabbitmq server is terminated here


Requirements
============
* Python 2.7, 3.4, 3.5, 3.6

License
=======
Apache License 2.0


History
=======

1.0.0 (2019-08-19)
-------------------
* First release

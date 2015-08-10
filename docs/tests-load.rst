Load Testing with Locust
========================

We use Locust for load-testing MDN. We write locust test files for different
behavior patterns on MDN, and run the tests to simulate those behaviors
against other environments.

.. note:: **DO NOT RUN LOCUST TESTS AGAINST PRODUCTION**

Installing
----------

See `Installation Docs for Locust
<http://docs.locust.io/en/latest/installation.html>`_. (Notice there
are some platform-specific instructions.)

Running Tests
-------------

.. note:: **DO NOT RUN LOCUST TESTS AGAINST PRODUCTION**

1. Start locust with one of our test files and our target host::

    locust -f tests/load/smoke.py --host=https://developer.allizom.org

2. Go to `http://127.0.0.1:8089/ <http://127.0.0.1:8089/>`_ UI for controlling:

  * number of users to simulate
  * users spawned per second

See `Start locust
<http://docs.locust.io/en/latest/quickstart.html#start-locust>`_ for more.

Adding a Test Suite
-------------------

See `Writing a locustfile
<http://docs.locust.io/en/latest/writing-a-locustfile.html>`_ for more.

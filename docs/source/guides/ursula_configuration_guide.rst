Ursula Configuration Guide
==========================

Before continuing, Verify your ``nucypher`` installation and entry points are functional:

Activate your virtual environment and run the ``nucypher --help`` command

.. code:: bash

    $ source nucypher/bin/activate
    ...
    (nucypher)$ nucypher --help


You will see a list of possible usage options (``--version``, ``-v``, ``--dev``, etc.) and commands (``status``, ``ursula``).
For example, you can use ``nucypher ursula destroy`` to delete all files associated with the node.

If your installation in non-functional, be sure you have the latest version installed, and see the `Installation Guide`_

.. _Installation Guide: installation_guide.html



2. Configure a new Ursula node

*Decentralized Ursula Configuration*

.. code:: bash

    (nucypher)$ nucypher ursula init --provider <YOUR PROVIDER URI> --network <NETWORK NAME> --poa


Replace ``<YOUR PROVIDER URI>`` with a valid node web3 node provider string, for example:

    - ``file:///tmp/geth.ipc``   - Geth Development Node
    - ``http://localhost:7545`` - Ganache TestRPC (HTTP-JSON-RPC)
    - ``ws://0.0.0.0:8080``     - Websocket Provider


3. Enter or confirm your public-facing IPv4 address when prompted

.. code:: bash

    Enter Nodes Public IPv4 Address: <YOUR NODE IP HERE>


4. Create a password when prompted

.. code:: bash

    Enter a password to encrypt your keyring: <YOUR PASSWORD HERE>


.. important::::
    Save your password as you will need it to relaunch the node, and please note:

    - Minimum password length is 16 characters
    - Do not use a password that you use anywhere else

5. Connect to a Fleet

.. code:: bash

    (nucypher)$ nucypher ursula run --teacher <SEEDNODE_URI> --interactive


6. Verify Ursula Blockchain Connection (Interactive)

This will drop your terminal session into the “Ursula Interactive Console” indicated by the ``>>>``.
Verify that the node setup was successful by running the ``status`` command.

.. code:: bash

    Ursula >>> status


7. To view a list of known Ursulas, execute the ``known_nodes`` command

.. code:: bash

    Ursula >>> known_nodes


You can also view your node’s network status webpage by navigating your web browser to ``https://<your-node-ip-address>:9151/status``.

.. NOTE::
    Since Ursulas self-sign TLS certificates, you may receive a warning from your web browser.


8. To stop your node from the interactive console and return to the terminal session:

.. code:: bash

    Ursula >>> stop


9. Subsequent node restarts do not need the teacher endpoint specified:

.. code:: bash

    (nucypher)$ nucypher ursula run --poa

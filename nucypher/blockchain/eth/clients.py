import json
import os
import shutil
import time
import maya

from constant_sorrow.constants import NOT_RUNNING
from eth_utils import to_checksum_address, is_checksum_address
from geth import LoggingMixin
from geth.accounts import get_accounts, create_new_account
from geth.chain import (
    get_chain_data_dir,
    initialize_chain,
    is_live_chain,
    is_ropsten_chain
)
from geth.process import BaseGethProcess
from twisted.logger import Logger
from web3 import Web3
from web3.exceptions import BlockNotFound

from nucypher.config.constants import DEFAULT_CONFIG_ROOT, DEPLOY_DIR, USER_LOG_DIR

NUCYPHER_CHAIN_IDS = {
    'devnet': 112358,
}


class Web3ClientError(Exception):
    pass


class Web3ClientConnectionFailed(Web3ClientError):
    pass


class Web3ClientUnexpectedVersionString(Web3ClientError):
    pass


class Web3Client(object):

    is_local = False

    @classmethod
    def from_w3(cls, w3: Web3, *args):
        #
        # *Client version format*
        # Geth Example: "'Geth/v1.4.11-stable-fed692f6/darwin/go1.7'"
        # Parity Example: "Parity//v1.5.0-unstable-9db3f38-20170103/x86_64-linux-gnu/rustc1.14.0"
        # Ganache Example: "EthereumJS TestRPC/v2.1.5/ethereum-js"
        #
        client_data = w3.clientVersion.split('/')
        node_technology = client_data[0]

        GETH = 'Geth'
        PARITY = 'Parity'
        GANACHE = 'EthereumJS TestRPC'
        ETHEREUM_TESTER = 'EthereumTester'

        try:
            subcls = {
                GETH: GethClient,
                PARITY: ParityClient,
                GANACHE: GanacheClient,
                ETHEREUM_TESTER: EthTestClient,
            }[node_technology]
        except KeyError:
            raise NotImplementedError(node_technology)
        return subcls(w3, *client_data)

    class ConnectionNotEstablished(RuntimeError):
        pass

    class SyncTimeout(RuntimeError):
        pass

    def __init__(self, w3, node_technology, version, backend, *args, **kwargs):
        self.w3 = w3
        self.node_technology = node_technology
        self.node_version = version
        self.backend = backend

        self.log = Logger("blockchain")

    @property
    def peers(self):
        raise NotImplementedError

    @property
    def syncing(self):
        return self.w3.eth.syncing

    def unlock_account(self, address, password):
        raise NotImplementedError

    def unlockAccount(self, address, password):
        return self.unlock_account(address, password)

    def is_connected(self):
        return self.w3.isConnected()

    @property
    def accounts(self):
        return self.w3.eth.accounts

    def getBalance(self, address):
        return self.w3.eth.getBalance(address)

    @property
    def chainId(self):
        return self.w3.net.chainId

    def sync(self, timeout: int = 600):

        # Record start time for timeout calculation
        now = maya.now()
        start_time = now

        def check_for_timeout(timeout=timeout):
            last_update = maya.now()
            duration = (last_update - start_time).seconds
            if duration > timeout:
                raise self.SyncTimeout

        # Check for ethereum peers
        self.log.info(f"Waiting for ethereum peers...")
        while not self.peers:
            time.sleep(0)
            check_for_timeout(timeout=30)

        needs_sync = False
        for peer in self.peers:
            peer_block_header = peer['protocols']['eth']['head']
            try:
                self.w3.eth.getBlock(peer_block_header)
            except BlockNotFound:
                needs_sync = True
                break

        # Start
        if needs_sync:
            peers = len(self.peers)
            self.log.info(f"Waiting for sync to begin ({peers} ethereum peers)")
            while not self.syncing:
                time.sleep(0)
                check_for_timeout()

            # Continue until done
            while self.syncing:
                current = self.syncing['currentBlock']
                total = self.syncing['highestBlock']
                self.log.info(f"Syncing {current}/{total}")
                time.sleep(1)
                check_for_timeout()

            return True


class GethClient(Web3Client):

    @property
    def peers(self):
        return self.w3.geth.admin.peers()

    def unlock_account(self, address, password):
        return self.w3.geth.personal.unlockAccount(address, password)


class ParityClient(Web3Client):

    def __init__(self, w3, node_technology, blank, version, backend, *args):
        super().__init__(w3, node_technology, version, backend)


    @property
    def peers(self) -> list:
        return self.w3.manager.request_blocking("parity_netPeers", [])

    def unlock_account(self, address, password):
        return self.w3.parity.unlockAccount.unlockAccount(address, password)


class GanacheClient(Web3Client):

    def __init__(self, w3, node_technology, version, backend, *args):
        super().__init__(self, w3, node_technology, version, backend)

    is_local = True

    def unlock_account(self, address, password):
        return True

    def sync(self, *args, **kwargs):
        return True


class EthTestClient(Web3Client):

    is_local = True

    def unlock_account(self, address, password):
        return True

    def sync(self, *args, **kwargs):
        return True

    def __init__(self, w3, node_technology, version, backend, *args, **kwargs):
        self.w3 = w3
        self.node_technology = node_technology
        self.node_version = version
        self.backend = backend
        self.log = Logger("blockchain")


class NuCypherGethProcess(LoggingMixin, BaseGethProcess):
    IPC_PROTOCOL = 'http'
    IPC_FILENAME = 'geth.ipc'
    VERBOSITY = 5
    LOG_PATH = os.path.join(USER_LOG_DIR, 'nucypher-geth.log')

    _CHAIN_NAME = NotImplemented

    def __init__(self,
                 geth_kwargs: dict,
                 stdout_logfile_path: str = LOG_PATH,
                 stderr_logfile_path: str = LOG_PATH,
                 *args, **kwargs):

        super().__init__(geth_kwargs=geth_kwargs,
                         stdout_logfile_path=stdout_logfile_path,
                         stderr_logfile_path=stderr_logfile_path,
                         *args, **kwargs)

        self.log = Logger('nucypher-geth')

    @property
    def provider_uri(self, scheme: str = None) -> str:
        if not scheme:
            scheme = self.IPC_PROTOCOL
        if scheme == 'file':
            location = self.ipc_path
        elif scheme in ('http', 'ws'):
            location = f'{self.rpc_host}:{self.rpc_port}'
        else:
            raise ValueError(f'{scheme} is an unknown ethereum node IPC protocol.')

        uri = f"{scheme}://{location}"
        return uri

    def start(self, timeout: int = 30, extra_delay: int = 1):
        self.log.info("STARTING GETH NOW")
        super().start()
        self.wait_for_ipc(timeout=timeout)  # on for all nodes by default
        if self.IPC_PROTOCOL in ('rpc', 'http'):
            self.wait_for_rpc(timeout=timeout)
        time.sleep(extra_delay)


class NuCypherGethDevProcess(NuCypherGethProcess):

    _CHAIN_NAME = 'poa-development'

    def __init__(self, config_root: str = None, *args, **kwargs):

        base_dir = config_root if config_root else DEFAULT_CONFIG_ROOT
        base_dir = os.path.join(base_dir, '.ethereum')
        self.data_dir = get_chain_data_dir(base_dir=base_dir, name=self._CHAIN_NAME)

        ipc_path = os.path.join(self.data_dir, 'geth.ipc')
        self.geth_kwargs = {'ipc_path': ipc_path}
        super().__init__(geth_kwargs=self.geth_kwargs, *args, **kwargs)
        self.geth_kwargs.update({'dev': True})

        self.command = [*self.command, '--dev']


class NuCypherGethDevnetProcess(NuCypherGethProcess):

    IPC_PROTOCOL = 'file'
    GENESIS_FILENAME = 'testnet_genesis.json'
    GENESIS_SOURCE_FILEPATH = os.path.join(DEPLOY_DIR, GENESIS_FILENAME)

    P2P_PORT = 30303
    _CHAIN_NAME = 'devnet'
    __CHAIN_ID = NUCYPHER_CHAIN_IDS[_CHAIN_NAME]

    def __init__(self,
                 config_root: str = None,
                 overrides: dict = None,
                 *args, **kwargs):

        log = Logger('nucypher-geth-devnet')

        if overrides is None:
            overrides = dict()

        # Validate
        invalid_override = f"You cannot specify `network_id` for a {self.__class__.__name__}"
        if 'data_dir' in overrides:
            raise ValueError(invalid_override)
        if 'network_id' in overrides:
            raise ValueError(invalid_override)

        # Set the data dir
        if config_root is None:
            base_dir = os.path.join(DEFAULT_CONFIG_ROOT, '.ethereum')
        else:
            base_dir = os.path.join(config_root, '.ethereum')
        self.data_dir = get_chain_data_dir(base_dir=base_dir, name=self._CHAIN_NAME)

        # Hardcoded Geth CLI args for devnet child process ("light client")
        ipc_path = os.path.join(self.data_dir, self.IPC_FILENAME)
        geth_kwargs = {'network_id': str(self.__CHAIN_ID),
                       'port': str(self.P2P_PORT),
                       'verbosity': str(self.VERBOSITY),
                       'data_dir': self.data_dir,
                       'ipc_path': ipc_path,
                       'rpc_enabled': True,
                       'no_discover': True,
                       }

        # Genesis & Blockchain Init
        self.genesis_filepath = os.path.join(self.data_dir, self.GENESIS_FILENAME)
        needs_init = all((
            not os.path.exists(self.genesis_filepath),
            not is_live_chain(self.data_dir),
            not is_ropsten_chain(self.data_dir),
        ))

        if needs_init:
            log.debug("Local system needs geth blockchain initialization")
            self.initialized = False
        else:
            self.initialized = True

        self.__process = NOT_RUNNING
        super().__init__(geth_kwargs=geth_kwargs, *args, **kwargs)  # Attaches self.geth_kwargs in super call
        self.command = [*self.command, '--syncmode', 'fast']

    def get_accounts(self):
        accounts = get_accounts(**self.geth_kwargs)
        return accounts

    def initialize_blockchain(self, overwrite: bool = True) -> None:
        log = Logger('nucypher-geth-init')
        with open(self.GENESIS_SOURCE_FILEPATH, 'r') as file:
            genesis_data = json.loads(file.read())
            log.info(f"Read genesis file '{self.GENESIS_SOURCE_FILEPATH}'")

        genesis_data.update(dict(overwrite=overwrite))
        log.info(f'Initializing new blockchain database and genesis block.')
        initialize_chain(genesis_data=genesis_data, **self.geth_kwargs)

        # Write static nodes file to data dir
        bootnodes_filepath = os.path.join(DEPLOY_DIR, 'static-nodes.json')
        shutil.copy(bootnodes_filepath, os.path.join(self.data_dir))

    def ensure_account_exists(self, password: str) -> str:
        accounts = get_accounts(**self.geth_kwargs)
        if not accounts:
            account = create_new_account(password=password.encode(), **self.geth_kwargs)
        else:
            account = accounts[0]

        checksum_address = to_checksum_address(account.decode())
        assert is_checksum_address(checksum_address), f"GETH RETURNED INVALID ETH ADDRESS {checksum_address}"
        return checksum_address

    def start(self, *args, **kwargs):
        # FIXME: Quick and Dirty

        # Write static nodes file to data dir
        bootnodes_filepath = os.path.join(DEPLOY_DIR, 'static-nodes.json')
        shutil.copy(bootnodes_filepath, os.path.join(self.data_dir))
        super().start()

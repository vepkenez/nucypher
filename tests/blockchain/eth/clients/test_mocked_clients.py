from nucypher.blockchain.eth.clients import (
    GethClient,
    ParityClient,
    GanacheClient,
    InfuraClient,
    PUBLIC_CHAINS
)
from nucypher.blockchain.eth.interfaces import BlockchainInterface


#
# Mock Providers
#

class MockGethProvider:
    endpoint_uri = 'file:///ipc.geth'
    clientVersion = 'Geth/v1.4.11-stable-fed692f6/darwin/go1.7'


class MockParityProvider:
    endpoint_uri = 'file:///ipc.parity'
    clientVersion = 'Parity-Ethereum/v2.5.1-beta-e0141f8-20190510/x86_64-linux-gnu/rustc1.34.1'


class MockGanacheProvider:
    endpoint_uri = 'http://ganache:8445'
    clientVersion = 'EthereumJS TestRPC/v2.1.5/ethereum-js'


class MockInfuraProvider:
    endpoint_uri = 'wss://:@goerli.infura.io/ws/v3/1234567890987654321abcdef'
    clientVersion = 'Geth/v1.8.23-omnibus-2ad89aaa/linux-amd64/go1.11.1'


class ChainIdReporter:
    # Support older and newer versions of web3 py in-test
    version = 5
    chainID = 5


#
# Mock Web3
#

class MockWeb3:

    net = ChainIdReporter

    def __init__(self, provider):
        self.provider = provider

    @property
    def clientVersion(self):
        return self.provider.clientVersion


#
# Mock Blockchain
#

class BlockchainInterfaceTestBase(BlockchainInterface):

    Web3 = MockWeb3

    def _configure_registry(self, *args, **kwargs):
        pass

    def _setup_solidity(self, *args, **kwargs):
        pass

    def attach_middleware(self):
        pass


class InfuraTestClient(BlockchainInterfaceTestBase):

    def _attach_provider(self, *args, **kwargs) -> None:
        super()._attach_provider(provider=MockInfuraProvider())


class GethClientTestBlockchain(BlockchainInterfaceTestBase):

    def _attach_provider(self, *args, **kwargs) -> None:
        super()._attach_provider(provider=MockGethProvider())

    @property
    def is_local(self):
        return int(self.w3.net.version) not in PUBLIC_CHAINS


class ParityClientTestInterface(BlockchainInterfaceTestBase):

    def _attach_provider(self, *args, **kwargs) -> None:
        super()._attach_provider(provider=MockParityProvider())


class GanacheClientTestInterface(BlockchainInterfaceTestBase):

    def _attach_provider(self, *args, **kwargs) -> None:
        super()._attach_provider(provider=MockGanacheProvider())


def test_geth_web3_client():
    interface = GethClientTestBlockchain(provider_uri='file:///ipc.geth')
    interface.connect(fetch_registry=False, sync_now=False)

    assert isinstance(interface.client, GethClient)
    assert interface.client.node_technology == 'Geth'
    assert interface.client.node_version == 'v1.4.11-stable-fed692f6'
    assert interface.client.platform == 'darwin'
    assert interface.client.backend == 'go1.7'

    assert interface.client.is_local is False
    assert interface.client.chain_id == 5


def test_infura_web3_client():
    interface = InfuraTestClient(provider_uri='infura://1234567890987654321abcdef')
    interface.connect(fetch_registry=False, sync_now=False)

    assert isinstance(interface.client, InfuraClient)
    assert interface.node_version == 'v1.8.23-omnibus-2ad89aaa'
    assert interface.platform == 'linux-amd64'
    assert interface.backend == 'go1.11.1'

    assert interface.is_local is False
    assert interface.chain_id == 5

    assert interface.unlock_account('address', 'password')  # should return True


def test_parity_web3_client():
    interface = ParityClientTestInterface(provider_uri='file:///ipc.parity')
    interface.connect(fetch_registry=False, sync_now=False)

    assert isinstance(interface.client, ParityClient)
    assert interface.client.node_technology == 'Parity-Ethereum'
    assert interface.client.node_version == 'v2.5.1-beta-e0141f8-20190510'
    assert interface.client.platform == 'x86_64-linux-gnu'
    assert interface.client.backend == 'rustc1.34.1'


def test_ganache_web3_client():
    interface = GanacheClientTestInterface(provider_uri='http://ganache:8445')
    interface.connect(fetch_registry=False, sync_now=False)

    assert isinstance(interface.client, GanacheClient)
    assert interface.client.node_technology == 'EthereumJS TestRPC'
    assert interface.client.node_version == 'v2.1.5'
    assert interface.client.platform is None
    assert interface.client.backend == 'ethereum-js'
    assert interface.client.is_local

import pytest
from nucypher.blockchain.eth.interfaces import BlockchainInterface
from nucypher.blockchain.eth.clients import (
    GethClient, ParityClient, GanacheClient, EthTestClient)


class MockGethProvider:

    clientVersion = 'Geth/v1.4.11-stable-fed692f6/darwin/go1.7'


class MockParityProvider:
    clientVersion = 'Parity//v1.5.0-unstable-9db3f38-20170103/x86_64-linux-gnu/rustc1.14.0'


class MockGanacheProvider:
    clientVersion = 'EthereumJS TestRPC/v2.1.5/ethereum-js'


class MockWeb3():

    def __init__(self, provider):
        self.provider = provider

    @property
    def clientVersion(self):
        return self.provider.clientVersion


class BlockChainInterfaceTestBase(BlockchainInterface):

    Web3 = MockWeb3

    def _configure_registry(self, *args, **kwargs):
        pass

    def _setup_solidity(self, *args, **kwargs):
        pass


class GethClientTestInterface(BlockChainInterfaceTestBase):

    def _get_IPC_provider(self):
        return MockGethProvider()


class ParityClientTestInterface(BlockChainInterfaceTestBase):

    def _get_IPC_provider(self):
        return MockParityProvider()


class GanacheClientTestInterface(BlockChainInterfaceTestBase):

    def _get_HTTP_provider(self):
        return MockGanacheProvider()


def test_geth_web3_client():
    interface = GethClientTestInterface(
        provider_uri='file:///ipc.geth'
    )
    assert isinstance(interface.client, GethClient)
    assert interface.backend == 'darwin'


def test_parity_web3_client():
    interface = ParityClientTestInterface(
        provider_uri='file:///ipc.parity'
    )
    assert isinstance(interface.client, ParityClient)
    assert interface.backend == 'x86_64-linux-gnu'


def test_ganache_web3_client():
    interface = GanacheClientTestInterface(
        provider_uri='http:///ganache:8445'
    )
    assert isinstance(interface.client, GanacheClient)
    assert interface.backend is None
    assert interface.is_local

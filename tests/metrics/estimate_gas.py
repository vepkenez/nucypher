#!/usr/bin/env python3


"""
This file is part of nucypher.

nucypher is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

nucypher is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with nucypher.  If not, see <https://www.gnu.org/licenses/>.
"""


import json
import os
from typing import List, Tuple

import time
from os.path import abspath, dirname

import io
import re
from twisted.logger import globalLogPublisher, Logger, jsonFileLogObserver, ILogObserver
from zope.interface import provider

from nucypher.blockchain.eth.actors import Deployer
from nucypher.blockchain.eth.agents import NucypherTokenAgent, MinerAgent, PolicyAgent
from nucypher.blockchain.eth.constants import (
    DISPATCHER_SECRET_LENGTH,
    MIN_ALLOWED_LOCKED,
    MIN_LOCKED_PERIODS,
    POLICY_ID_LENGTH
)
from nucypher.blockchain.eth.interfaces import BlockchainDeployerInterface
from nucypher.blockchain.eth.registry import InMemoryEthereumContractRegistry
from nucypher.blockchain.eth.sol.compile import SolidityCompiler
from nucypher.config.constants import CONTRACT_ROOT
from nucypher.utilities.sandbox.blockchain import TesterBlockchain


class AnalyzeGas:

    # Tweaks
    LOG_NAME = 'estimate-gas'
    LOG_FILENAME = '{}.log.json'.format(LOG_NAME)
    OUTPUT_DIR = os.path.join(abspath(dirname(__file__)), 'results')
    CONTRACT_DIR = CONTRACT_ROOT
    PROVIDER_URI = "tester://pyevm"
    TEST_ACCOUNTS = 10
    JSON_OUTPUT_FILENAME ='{}.json'.format(LOG_NAME)

    def __init__(self) -> None:
        self.gas_estimations = dict()

        if not os.path.isdir(self.OUTPUT_DIR):
            os.mkdir(self.OUTPUT_DIR)

    @provider(ILogObserver)
    def __call__(self, event, *args, **kwargs) -> None:
        if event.get('log_namespace') == self.LOG_NAME:
            message = event.get("log_format")
            if not re.match(r'\w+\s=\s\d+$', message):
                return
            label, gas = (s.strip() for s in message.split('='))
            self.paint_line(label, gas)
            self.gas_estimations[label] = int(gas)

    @staticmethod
    def paint_line(label: str, gas: str) -> None:
        print('{label} {dots} {gas:,}'.format(label=label, dots='.' * (65 - len(label)), gas=int(gas)))

    def to_json_file(self) -> None:
        print('Saving JSON Output...')

        epoch_time = str(int(time.time()))
        timestamped_filename = '{}-{}'.format(epoch_time, self.JSON_OUTPUT_FILENAME)
        filepath = os.path.join(self.OUTPUT_DIR, timestamped_filename)
        with open(filepath, 'w') as file:
            file.write(json.dumps(self.gas_estimations, indent=4))

    def start_collection(self) -> None:
        print("Starting Data Collection...")

        json_filepath = os.path.join(self.OUTPUT_DIR, AnalyzeGas.LOG_FILENAME)
        json_io = io.open(json_filepath, "w")
        json_observer = jsonFileLogObserver(json_io)
        globalLogPublisher.addObserver(json_observer)
        globalLogPublisher.addObserver(self)

    def connect_to_blockchain(self) -> TesterBlockchain:
        print("Deploying Blockchain...")

        solidity_compiler = SolidityCompiler(test_contract_dir=self.CONTRACT_DIR)
        memory_registry = InMemoryEthereumContractRegistry()
        interface = BlockchainDeployerInterface(provider_uri=self.PROVIDER_URI, compiler=solidity_compiler,
                                                registry=memory_registry)

        testerchain = TesterBlockchain(interface=interface, test_accounts=self.TEST_ACCOUNTS, airdrop=False)
        return testerchain

    @staticmethod
    def deploy_contracts(testerchain: TesterBlockchain) -> None:
        print("Deploying Contracts...")

        origin = testerchain.interface.w3.eth.accounts[0]
        deployer = Deployer(blockchain=testerchain, deployer_address=origin, bare=True)
        _txhashes, _agents = deployer.deploy_network_contracts(miner_secret=os.urandom(DISPATCHER_SECRET_LENGTH),
                                                               policy_secret=os.urandom(DISPATCHER_SECRET_LENGTH))

    @staticmethod
    def connect_to_contracts(testerchain: TesterBlockchain) -> Tuple[NucypherTokenAgent, MinerAgent, PolicyAgent]:
        print("Connecting...")

        token_agent = NucypherTokenAgent(blockchain=testerchain)
        miner_agent = MinerAgent(blockchain=testerchain)
        policy_agent = PolicyAgent(blockchain=testerchain)

        return token_agent, miner_agent, policy_agent

    def bootstrap_network(self) -> Tuple[TesterBlockchain, List[str]]:
        print("Bootstrapping testing network...")

        testerchain = self.connect_to_blockchain()
        self.deploy_contracts(testerchain=testerchain)
        return testerchain, testerchain.interface.w3.eth.accounts


def estimate_gas(analyzer: AnalyzeGas) -> AnalyzeGas:

    #
    # Setup
    #
    log = Logger(AnalyzeGas.LOG_NAME)

    testerchain, accounts = analyzer.bootstrap_network()
    web3 = testerchain.interface.w3

    token_agent, miner_agent, policy_agent = analyzer.connect_to_contracts(testerchain=testerchain)
    log.info("Running with provider URI: {}".format(testerchain.interface.provider_uri))

    analyzer.start_collection()

    #
    # Scenario
    #

    origin, ursula1, ursula2, ursula3, alice1, *everyone_else = testerchain.interface.w3.eth.accounts

    print("********* Estimating Gas *********")

    # Pre deposit tokens
    tx = token_agent.contract.functions.approve(miner_agent.contract_address, MIN_ALLOWED_LOCKED * 5).transact({'from': origin})
    testerchain.wait_for_receipt(tx)
    log.info("Pre-deposit tokens for 5 owners = " +
          str(miner_agent.contract.functions
              .preDeposit(everyone_else[0:5],
                          [MIN_ALLOWED_LOCKED] * 5,
                          [MIN_LOCKED_PERIODS] * 5)
              .estimateGas({'from': origin})))

    # Give Ursula and Alice some coins
    log.info("Transfer tokens = " +
          str(token_agent.contract.functions.transfer(ursula1, MIN_ALLOWED_LOCKED * 10)
              .estimateGas({'from': origin})))
    tx = token_agent.contract.functions.transfer(ursula1, MIN_ALLOWED_LOCKED * 10).transact({'from': origin})
    testerchain.wait_for_receipt(tx)
    tx = token_agent.contract.functions.transfer(ursula2, MIN_ALLOWED_LOCKED * 10).transact({'from': origin})
    testerchain.wait_for_receipt(tx)
    tx = token_agent.contract.functions.transfer(ursula3, MIN_ALLOWED_LOCKED * 10).transact({'from': origin})
    testerchain.wait_for_receipt(tx)

    # Ursula and Alice give Escrow rights to transfer
    log.info("Approving transfer = " +
          str(token_agent.contract.functions.approve(miner_agent.contract_address, MIN_ALLOWED_LOCKED * 6)
              .estimateGas({'from': ursula1})))
    tx = token_agent.contract.functions.approve(miner_agent.contract_address, MIN_ALLOWED_LOCKED * 6)\
        .transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    tx = token_agent.contract.functions.approve(miner_agent.contract_address, MIN_ALLOWED_LOCKED * 6)\
        .transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    tx = token_agent.contract.functions.approve(miner_agent.contract_address, MIN_ALLOWED_LOCKED * 6)\
        .transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    # Ursula and Alice transfer some tokens to the escrow and lock them
    log.info("First initial deposit tokens = " +
          str(miner_agent.contract.functions.deposit(MIN_ALLOWED_LOCKED * 3, MIN_LOCKED_PERIODS).estimateGas({'from': ursula1})))
    tx = miner_agent.contract.functions.deposit(MIN_ALLOWED_LOCKED * 3, MIN_LOCKED_PERIODS).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    log.info("Second initial deposit tokens = " +
          str(miner_agent.contract.functions.deposit(MIN_ALLOWED_LOCKED * 3, MIN_LOCKED_PERIODS).estimateGas({'from': ursula2})))
    tx = miner_agent.contract.functions.deposit(MIN_ALLOWED_LOCKED * 3, MIN_LOCKED_PERIODS).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    log.info("Third initial deposit tokens = " +
          str(miner_agent.contract.functions.deposit(MIN_ALLOWED_LOCKED * 3, MIN_LOCKED_PERIODS).estimateGas({'from': ursula3})))
    tx = miner_agent.contract.functions.deposit(MIN_ALLOWED_LOCKED * 3, MIN_LOCKED_PERIODS).transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    # Wait 1 period and confirm activity
    testerchain.time_travel(periods=1)
    log.info("First confirm activity = " +
          str(miner_agent.contract.functions.confirmActivity().estimateGas({'from': ursula1})))
    tx = miner_agent.contract.functions.confirmActivity().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    log.info("Second confirm activity = " +
          str(miner_agent.contract.functions.confirmActivity().estimateGas({'from': ursula2})))
    tx = miner_agent.contract.functions.confirmActivity().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    log.info("Third confirm activity = " +
          str(miner_agent.contract.functions.confirmActivity().estimateGas({'from': ursula3})))
    tx = miner_agent.contract.functions.confirmActivity().transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    # Wait 1 period and mint tokens
    testerchain.time_travel(periods=1)
    log.info("First mining (1 stake) = " + str(miner_agent.contract.functions.mint().estimateGas({'from': ursula1})))
    tx = miner_agent.contract.functions.mint().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    log.info("Second mining (1 stake) = " + str(miner_agent.contract.functions.mint().estimateGas({'from': ursula2})))
    tx = miner_agent.contract.functions.mint().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    log.info("Third/last mining (1 stake) = " + str(miner_agent.contract.functions.mint().estimateGas({'from': ursula3})))
    tx = miner_agent.contract.functions.mint().transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    log.info("First confirm activity again = " +
          str(miner_agent.contract.functions.confirmActivity().estimateGas({'from': ursula1})))
    tx = miner_agent.contract.functions.confirmActivity().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    log.info("Second confirm activity again = " +
          str(miner_agent.contract.functions.confirmActivity().estimateGas({'from': ursula2})))
    tx = miner_agent.contract.functions.confirmActivity().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    log.info("Third confirm activity again = " +
          str(miner_agent.contract.functions.confirmActivity().estimateGas({'from': ursula3})))
    tx = miner_agent.contract.functions.confirmActivity().transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    # Confirm again
    testerchain.time_travel(periods=1)
    log.info("First confirm activity + mint = " +
          str(miner_agent.contract.functions.confirmActivity().estimateGas({'from': ursula1})))
    tx = miner_agent.contract.functions.confirmActivity().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    log.info("Second confirm activity + mint = " +
          str(miner_agent.contract.functions.confirmActivity().estimateGas({'from': ursula2})))
    tx = miner_agent.contract.functions.confirmActivity().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    log.info("Third confirm activity + mint = " +
          str(miner_agent.contract.functions.confirmActivity().estimateGas({'from': ursula3})))
    tx = miner_agent.contract.functions.confirmActivity().transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    # Get locked tokens
    log.info("Getting locked tokens = " + str(miner_agent.contract.functions.getLockedTokens(ursula1).estimateGas()))

    # Wait 1 period and withdraw tokens
    testerchain.time_travel(periods=1)
    log.info("First withdraw = " + str(miner_agent.contract.functions.withdraw(1).estimateGas({'from': ursula1})))
    tx = miner_agent.contract.functions.withdraw(1).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    log.info("Second withdraw = " + str(miner_agent.contract.functions.withdraw(1).estimateGas({'from': ursula2})))
    tx = miner_agent.contract.functions.withdraw(1).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    log.info("Third withdraw = " + str(miner_agent.contract.functions.withdraw(1).estimateGas({'from': ursula3})))
    tx = miner_agent.contract.functions.withdraw(1).transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    # Wait 1 period and confirm activity
    testerchain.time_travel(periods=1)
    log.info("First confirm activity after downtime = " +
          str(miner_agent.contract.functions.confirmActivity().estimateGas({'from': ursula1})))
    tx = miner_agent.contract.functions.confirmActivity().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    log.info("Second confirm activity after downtime  = " +
          str(miner_agent.contract.functions.confirmActivity().estimateGas({'from': ursula2})))
    tx = miner_agent.contract.functions.confirmActivity().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    log.info("Third confirm activity after downtime  = " +
          str(miner_agent.contract.functions.confirmActivity().estimateGas({'from': ursula3})))
    tx = miner_agent.contract.functions.confirmActivity().transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    # Ursula and Alice deposit some tokens to the escrow again
    log.info("First deposit tokens again = " +
          str(miner_agent.contract.functions.deposit(MIN_ALLOWED_LOCKED * 2, MIN_LOCKED_PERIODS).estimateGas({'from': ursula1})))
    tx = miner_agent.contract.functions.deposit(MIN_ALLOWED_LOCKED * 2, MIN_LOCKED_PERIODS).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    log.info("Second deposit tokens again = " +
          str(miner_agent.contract.functions.deposit(MIN_ALLOWED_LOCKED * 2, MIN_LOCKED_PERIODS).estimateGas({'from': ursula2})))
    tx = miner_agent.contract.functions.deposit(MIN_ALLOWED_LOCKED * 2, MIN_LOCKED_PERIODS).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    log.info("Third deposit tokens again = " +
          str(miner_agent.contract.functions.deposit(MIN_ALLOWED_LOCKED * 2, MIN_LOCKED_PERIODS).estimateGas({'from': ursula3})))
    tx = miner_agent.contract.functions.deposit(MIN_ALLOWED_LOCKED * 2, MIN_LOCKED_PERIODS).transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    # Wait 1 period and mint tokens
    testerchain.time_travel(periods=1)
    log.info("First mining again = " + str(miner_agent.contract.functions.mint().estimateGas({'from': ursula1})))
    tx = miner_agent.contract.functions.mint().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    log.info("Second mining again = " + str(miner_agent.contract.functions.mint().estimateGas({'from': ursula2})))
    tx = miner_agent.contract.functions.mint().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    log.info("Third/last mining again = " + str(miner_agent.contract.functions.mint().estimateGas({'from': ursula3})))
    tx = miner_agent.contract.functions.mint().transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    # Create policy
    policy_id_1 = os.urandom(int(POLICY_ID_LENGTH))
    policy_id_2 = os.urandom(int(POLICY_ID_LENGTH))
    number_of_periods = 10
    log.info("First creating policy (1 node, 10 periods) = " +
          str(policy_agent.contract.functions.createPolicy(policy_id_1, number_of_periods, 0, [ursula1])
              .estimateGas({'from': alice1, 'value': 10000})))
    tx = policy_agent.contract.functions.createPolicy(policy_id_1, number_of_periods, 0, [ursula1])\
        .transact({'from': alice1, 'value': 10000})
    testerchain.wait_for_receipt(tx)
    log.info("Second creating policy (1 node, 10 periods) = " +
          str(policy_agent.contract.functions.createPolicy(policy_id_2, number_of_periods, 0, [ursula1])
              .estimateGas({'from': alice1, 'value': 10000})))
    tx = policy_agent.contract.functions.createPolicy(policy_id_2, number_of_periods, 0, [ursula1])\
        .transact({'from': alice1, 'value': 10000})
    testerchain.wait_for_receipt(tx)

    # Revoke policy
    log.info("Revoking policy = " +
          str(policy_agent.contract.functions.revokePolicy(policy_id_1).estimateGas({'from': alice1})))
    tx = policy_agent.contract.functions.revokePolicy(policy_id_1).transact({'from': alice1})
    testerchain.wait_for_receipt(tx)
    tx = policy_agent.contract.functions.revokePolicy(policy_id_2).transact({'from': alice1})
    testerchain.wait_for_receipt(tx)

    # Create policy with more periods
    policy_id_1 = os.urandom(int(POLICY_ID_LENGTH))
    policy_id_2 = os.urandom(int(POLICY_ID_LENGTH))
    policy_id_3 = os.urandom(int(POLICY_ID_LENGTH))
    number_of_periods = 100
    log.info("First creating policy (1 node, " + str(number_of_periods) + " periods, first reward) = " +
          str(policy_agent.contract.functions.createPolicy(policy_id_1, number_of_periods, 50, [ursula2])
              .estimateGas({'from': alice1, 'value': 10050})))
    tx = policy_agent.contract.functions.createPolicy(policy_id_1, number_of_periods, 50, [ursula2])\
        .transact({'from': alice1, 'value': 10050})
    testerchain.wait_for_receipt(tx)
    testerchain.time_travel(periods=1)
    log.info("Second creating policy (1 node, " + str(number_of_periods) + " periods, first reward) = " +
          str(policy_agent.contract.functions.createPolicy(policy_id_2, number_of_periods, 50, [ursula2])
              .estimateGas({'from': alice1, 'value': 10050})))
    tx = policy_agent.contract.functions.createPolicy(policy_id_2, number_of_periods, 50, [ursula2])\
        .transact({'from': alice1, 'value': 10050})
    testerchain.wait_for_receipt(tx)
    log.info("Third creating policy (1 node, " + str(number_of_periods) + " periods, first reward) = " +
          str(policy_agent.contract.functions.createPolicy(policy_id_3, number_of_periods, 50, [ursula1])
              .estimateGas({'from': alice1, 'value': 10050})))
    tx = policy_agent.contract.functions.createPolicy(policy_id_3, number_of_periods, 50, [ursula1])\
        .transact({'from': alice1, 'value': 10050})
    testerchain.wait_for_receipt(tx)

    # Mine and revoke policy
    testerchain.time_travel(periods=10)
    tx = miner_agent.contract.functions.confirmActivity().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    tx = miner_agent.contract.functions.confirmActivity().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)

    testerchain.time_travel(periods=1)
    log.info("First mining after downtime = " + str(miner_agent.contract.functions.mint().estimateGas({'from': ursula1})))
    tx = miner_agent.contract.functions.mint().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    log.info("Second mining after downtime = " + str(miner_agent.contract.functions.mint().estimateGas({'from': ursula2})))
    tx = miner_agent.contract.functions.mint().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)

    testerchain.time_travel(periods=10)
    log.info("First revoking policy after downtime = " +
          str(policy_agent.contract.functions.revokePolicy(policy_id_1).estimateGas({'from': alice1})))
    tx = policy_agent.contract.functions.revokePolicy(policy_id_1).transact({'from': alice1})
    testerchain.wait_for_receipt(tx)
    log.info("Second revoking policy after downtime = " +
          str(policy_agent.contract.functions.revokePolicy(policy_id_2).estimateGas({'from': alice1})))
    tx = policy_agent.contract.functions.revokePolicy(policy_id_2).transact({'from': alice1})
    testerchain.wait_for_receipt(tx)
    log.info("Second revoking policy after downtime = " +
          str(policy_agent.contract.functions.revokePolicy(policy_id_3).estimateGas({'from': alice1})))
    tx = policy_agent.contract.functions.revokePolicy(policy_id_3).transact({'from': alice1})
    testerchain.wait_for_receipt(tx)

    # Create policy with multiple nodes
    policy_id_1 = os.urandom(int(POLICY_ID_LENGTH))
    policy_id_2 = os.urandom(int(POLICY_ID_LENGTH))
    policy_id_3 = os.urandom(int(POLICY_ID_LENGTH))
    number_of_periods = 100
    log.info("First creating policy (3 nodes, 100 periods, first reward) = " +
          str(policy_agent.contract.functions
              .createPolicy(policy_id_1, number_of_periods, 50, [ursula1, ursula2, ursula3])
              .estimateGas({'from': alice1, 'value': 30150})))
    tx = policy_agent.contract.functions.createPolicy(policy_id_1, number_of_periods, 50, [ursula1, ursula2, ursula3])\
        .transact({'from': alice1, 'value': 30150})
    testerchain.wait_for_receipt(tx)
    log.info("Second creating policy (3 nodes, 100 periods, first reward) = " +
          str(policy_agent.contract.functions
              .createPolicy(policy_id_2, number_of_periods, 50, [ursula1, ursula2, ursula3])
              .estimateGas({'from': alice1, 'value': 30150})))
    tx = policy_agent.contract.functions.createPolicy(policy_id_2, number_of_periods, 50, [ursula1, ursula2, ursula3])\
        .transact({'from': alice1, 'value': 30150})
    testerchain.wait_for_receipt(tx)
    log.info("Third creating policy (2 nodes, 100 periods, first reward) = " +
          str(policy_agent.contract.functions.createPolicy(policy_id_3, number_of_periods, 50, [ursula1, ursula2])
              .estimateGas({'from': alice1, 'value': 20100})))
    tx = policy_agent.contract.functions.createPolicy(policy_id_3, number_of_periods, 50, [ursula1, ursula2])\
        .transact({'from': alice1, 'value': 20100})
    testerchain.wait_for_receipt(tx)

    for index in range(5):
        tx = miner_agent.contract.functions.confirmActivity().transact({'from': ursula1})
        testerchain.wait_for_receipt(tx)
        tx = miner_agent.contract.functions.confirmActivity().transact({'from': ursula2})
        testerchain.wait_for_receipt(tx)
        tx = miner_agent.contract.functions.confirmActivity().transact({'from': ursula3})
        testerchain.wait_for_receipt(tx)
        testerchain.time_travel(periods=1)

    tx = miner_agent.contract.functions.mint().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    tx = miner_agent.contract.functions.mint().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    tx = miner_agent.contract.functions.mint().transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    # Check regular deposit
    log.info("First deposit tokens = " + str(miner_agent.contract.functions.deposit(MIN_ALLOWED_LOCKED, MIN_LOCKED_PERIODS).estimateGas({'from': ursula1})))
    tx = miner_agent.contract.functions.deposit(MIN_ALLOWED_LOCKED, MIN_LOCKED_PERIODS).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    log.info("Second deposit tokens = " + str(miner_agent.contract.functions.deposit(MIN_ALLOWED_LOCKED, MIN_LOCKED_PERIODS).estimateGas({'from': ursula2})))
    tx = miner_agent.contract.functions.deposit(MIN_ALLOWED_LOCKED, MIN_LOCKED_PERIODS).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    log.info("Third deposit tokens = " + str(miner_agent.contract.functions.deposit(MIN_ALLOWED_LOCKED, MIN_LOCKED_PERIODS).estimateGas({'from': ursula3})))
    tx = miner_agent.contract.functions.deposit(MIN_ALLOWED_LOCKED, MIN_LOCKED_PERIODS).transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    # ApproveAndCall
    testerchain.time_travel(periods=1)

    tx = miner_agent.contract.functions.mint().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    tx = miner_agent.contract.functions.mint().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    tx = miner_agent.contract.functions.mint().transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    log.info("First approveAndCall = " +
          str(token_agent.contract.functions.approveAndCall(miner_agent.contract_address,
                                                            MIN_ALLOWED_LOCKED * 2,
                                                            web3.toBytes(MIN_LOCKED_PERIODS))
              .estimateGas({'from': ursula1})))
    tx = token_agent.contract.functions.approveAndCall(miner_agent.contract_address,
                                                       MIN_ALLOWED_LOCKED * 2,
                                                       web3.toBytes(MIN_LOCKED_PERIODS)).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    log.info("Second approveAndCall = " +
          str(token_agent.contract.functions.approveAndCall(miner_agent.contract_address,
                                                            MIN_ALLOWED_LOCKED * 2,
                                                            web3.toBytes(MIN_LOCKED_PERIODS)).estimateGas({'from': ursula2})))
    tx = token_agent.contract.functions.approveAndCall(miner_agent.contract_address,
                                                       MIN_ALLOWED_LOCKED * 2,
                                                       web3.toBytes(MIN_LOCKED_PERIODS)).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    log.info("Third approveAndCall = " +
          str(token_agent.contract.functions.approveAndCall(miner_agent.contract_address,
                                                            MIN_ALLOWED_LOCKED * 2,
                                                            web3.toBytes(MIN_LOCKED_PERIODS))
              .estimateGas({'from': ursula3})))
    tx = token_agent.contract.functions.approveAndCall(miner_agent.contract_address,
                                                       MIN_ALLOWED_LOCKED * 2,
                                                       web3.toBytes(MIN_LOCKED_PERIODS)).transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    # Locking tokens
    testerchain.time_travel(periods=1)

    tx = miner_agent.contract.functions.confirmActivity().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    tx = miner_agent.contract.functions.confirmActivity().transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    tx = miner_agent.contract.functions.confirmActivity().transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    log.info("First locking tokens = " +
          str(miner_agent.contract.functions.lock(MIN_ALLOWED_LOCKED, MIN_LOCKED_PERIODS).estimateGas({'from': ursula1})))
    tx = miner_agent.contract.functions.lock(MIN_ALLOWED_LOCKED, MIN_LOCKED_PERIODS).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    log.info("Second locking tokens = " +
          str(miner_agent.contract.functions.lock(MIN_ALLOWED_LOCKED, MIN_LOCKED_PERIODS).estimateGas({'from': ursula2})))
    tx = miner_agent.contract.functions.lock(MIN_ALLOWED_LOCKED,MIN_LOCKED_PERIODS).transact({'from': ursula2})
    testerchain.wait_for_receipt(tx)
    log.info("Third locking tokens = " +
          str(miner_agent.contract.functions.lock(MIN_ALLOWED_LOCKED, MIN_LOCKED_PERIODS).estimateGas({'from': ursula3})))
    tx = miner_agent.contract.functions.lock(MIN_ALLOWED_LOCKED, MIN_LOCKED_PERIODS).transact({'from': ursula3})
    testerchain.wait_for_receipt(tx)

    # Divide stake
    log.info("First divide stake = " +
          str(miner_agent.contract.functions.divideStake(1, MIN_ALLOWED_LOCKED, 2)
              .estimateGas({'from': ursula1})))
    tx = miner_agent.contract.functions.divideStake(1, MIN_ALLOWED_LOCKED, 2).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    log.info("Second divide stake = " +
          str(miner_agent.contract.functions.divideStake(3, MIN_ALLOWED_LOCKED, 2)
              .estimateGas({'from': ursula1})))
    tx = miner_agent.contract.functions.divideStake(3, MIN_ALLOWED_LOCKED, 2).transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)

    # Divide almost finished stake
    testerchain.time_travel(periods=1)
    tx = miner_agent.contract.functions.confirmActivity().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    testerchain.time_travel(periods=1)
    log.info("Divide stake (next period is not confirmed) = " +
          str(miner_agent.contract.functions.divideStake(0, MIN_ALLOWED_LOCKED, 2)
              .estimateGas({'from': ursula1})))
    tx = miner_agent.contract.functions.confirmActivity().transact({'from': ursula1})
    testerchain.wait_for_receipt(tx)
    log.info("Divide stake (next period is confirmed) = " +
          str(miner_agent.contract.functions.divideStake(0, MIN_ALLOWED_LOCKED, 2)
              .estimateGas({'from': ursula1})))
    print("********* All Done! *********")
    return analyzer


if __name__ == "__main__":
    print("Starting Up...")
    analyzer = AnalyzeGas()
    analyzer = estimate_gas(analyzer=analyzer)
    analyzer.to_json_file()

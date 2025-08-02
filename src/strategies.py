# from ape.contracts import Contract
# from ape.types import AddressType

# TEND_TRIGGER_ABI = [
#     {
#         "name": "tendTrigger",
#         "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
#         "inputs": [],
#         "stateMutability": "view",
#         "type": "function"
#     }
# ]

# def strategy_needs_tending(address: AddressType) -> bool:
#     contract = Contract(address, abi=TEND_TRIGGER_ABI)
#     return contract.tendTrigger()
import json, contracts, argparse, table_manager, sys
from collections import OrderedDict
from data_models import Ask, Bid, Trade
from web3 import Web3
import endpoints as data
import streamlit as st
import matplotlib.pyplot as plt

# parse nft id from a longer string
def parse_nft_id(tokensetID: str) -> str:
    split = tokensetID.split(":", 2)

    return split[2]

# converts various ways of spelling marketplaces into the names accepted by the reservoir.tools API
def convert_marketplace_name(input: str) -> str:
    OS = "OpenSea"
    LR = "LooksRare"
    X2 = "X2Y2"

    conversions = {
        "Opensea": OS,
        "opensea": OS,
        "seaport": OS,
        "Looksrare": LR,
        "looksrare": LR,
        "looks-rare": LR,
        "x2y2": X2
    }

    return conversions[input]

# process marketplace names
def process_marketplace_names(marketplaces: list):
    adding_more = True
    while adding_more:
        try:
            name = input("Exchange name (opensea, looksrare, x2y2): ")
            adding_more = (input("add another marketplace? [Y/n]: ") == "Y")
            marketplaces.append(convert_marketplace_name(name))
        except:
            print("invalid exchange name entered")
            return process_marketplace_names()

# gets user input in compliance w/ reservoir.tools accepted marketplace names
def get_input_names() -> str:
    marketplaces = []

    process_marketplace_names(marketplaces)

    return marketplaces

# returns a project name from a contract address
def name_from_contract(contract: str) -> str:
    contract_to_name = {v: k for k, v in contracts.contract_data.items()}

    return contract_to_name[contract]

# gets project contract address from project name
def get_contract_address(verbose: bool = True) -> str:
    contract_data = contracts.contract_data

    if verbose:
        print("Contracts")
        for contract in contract_data.keys():
            print(contract + ": " + contract_data[contract])

    project_name = input("Project Name: ")

    try:
        return contract_data[project_name]
    except:
        print("invalid project name")
        return get_contract_address(verbose = False)

# fills the marketplace orders dict with the keys for the appropriate NFT prices
def fill_dict(start: int, end: int) -> dict:
    dictionary = {}
    for i in range(start, end+1):
        dictionary[i] = 0

    return dictionary

# gets data type from command line arguments
def get_data_type(arguments: bool = True) -> str:
    if arguments:
        parser = argparse.ArgumentParser()
        parser.add_argument('--data_type', dest='data_type', type=str, help='data type to get data about')
        args = parser.parse_args()

    if args.data_type != None:
        choice = args.data_type
    else:
        choice = input("ask, ask distribution, bid, or trade data: ")

    conversions = {
        "Bids":"bids",
        "Bid":"bids",
        "bid":"bids",
        "bids":"bids",
        "b":"bids",
        "Asks":"asks",
        "Ask":"asks",
        "asks":"asks",
        "ask":"asks",
        "a":"asks",
        "Trades":"trades",
        "Trade":"trades",
        "trade":"trades",
        "trades":"trades",
        "t":"trades",
        "ask_distribution":"ask_distribution",
        "ask-distribution":"ask_distribution",
        "ask distribution": "ask_distribution"
    }

    try:
        return conversions[choice]
    except:
        print("invalid data type")
        return get_data_type(arguments = False)

# inserts data into table
def insert_data(detailed_data: list, type: str) -> None:
    for detailed_piece_of_data in detailed_data:
        try:
            table_manager.insert_order(detailed_piece_of_data, type)
        except:
            sys.exit("writing data failed -- try resetting database file")

# creates a bar chart
def bar_chart(marketplace_listings: dict) -> None:
    project = name_from_contract(contract)
    marketplaces = list(marketplace_listings.keys())
    listings = list(marketplace_listings.values())

    figure = plt.figure(figsize = (10, 5))

    plt.bar(marketplaces, listings)
    plt.xlabel("Marketplace")
    plt.ylabel("# of Listings")
    plt.title(f"# of Listings for {project} Across Marketplaces")

    st.pyplot(figure)

# converts ask JSON data to ask objects
def parse_asks(orders: list, marketplace_asks: json, detailed_asks: list, min_price: int, max_price: int) -> None:
    for ask in orders:
        try:
            marketplace = ask["source"]["name"]
        except:
            marketplace = convert_marketplace_name(ask["kind"])

        project_name = ask['metadata']['data']['collectionName']
        nft_id = parse_nft_id(ask["tokenSetId"])
        currency = "ETH"
        price = ask["price"]
        created_at = ask["createdAt"]
        expires_on = ask["expiration"]
        maker = ask["maker"]

        value = int(round(price, 0))

        if marketplace in target_marketplaces and ask["tokenSetId"] not in token_ids and value >= min_price and value <= max_price: # only look at asks on the given marketplace that haven't been added yet below the max price
            if value in marketplace_asks.keys(): # if the rounded value of the ask is already a key in the dict, increment it. Otherwise create a new key
                marketplace_asks[value] += 1
            else:
                marketplace_asks[value] = 1

            order = Ask(project_name, nft_id, currency, price, marketplace, created_at, expires_on, maker, "ETH")
            detailed_asks.append(order)
            
            token_ids.append(ask["tokenSetId"])

# converts bid JSON data to bid objects
def parse_looksrare_bids(bids: list, detailed_bids: list) -> None:
    makers = []
    for bid in bids:
        marketplace = "LooksRare"
        project_name = name_from_contract(bid["collectionAddress"])
        currency = "ETH"
        price = str(float(bid["price"])/(10**18))
        created_at = bid["startTime"]
        maker = bid["signer"]
        
        strategy = bid["strategy"]
        if strategy == "0x56244Bb70CbD3EA9Dc8007399F61dFC065190031":
            bid_type = "single"
        else:
            bid_type = "collection"

        if bid["hash"] not in token_ids:
            if bid_type == "single":
                nft_id = bid["tokenId"]
            else:
                nft_id = "N/A"

            parsed_bid = Bid(project_name, nft_id, currency, price, marketplace, created_at, maker, bid_type, "ETH")
            detailed_bids.append(parsed_bid)

            token_ids.append(bid["hash"])
            makers.append(maker)

# converts trade JSON data to a trade object
def parse_trades(trades: list, detailed_trades: list) -> None:
    for trade in trades:
        project_name = name_from_contract(Web3.toChecksumAddress(trade["token"]["contract"]))
        id = trade["token"]["tokenId"]
        currency = "ETH"
        price = trade["price"]
        marketplace = trade["orderSource"]
        trade_timestamp = trade["timestamp"]
        buyer = trade["from"]
        seller = trade["to"]
        tx_id = trade["txHash"]
        offer_type = trade["orderSide"]
        
        fee_rate = 0
        if marketplace == "OpenSea":
            fee_rate = 0.025
        if marketplace == "LooksRare":
            fee_rate = 0.02
        if marketplace == "X2Y2":
            fee_rate = 0.005

        usdPrice = trade["usdPrice"]
        try:
            fee = usdPrice*fee_rate
        except:
            fee = 0

        if marketplace in target_marketplaces and trade["id"] not in token_ids:
            parsed_trade = Trade(project_name, id, currency, price, marketplace, trade_timestamp, buyer, seller, "ETH", tx_id, offer_type, fee)
            detailed_trades.append(parsed_trade)

            token_ids.append(trade["id"])

# manage asks
def manage_asks(verbose: bool = True) -> list:
    min_price = data.get_floor_price(contract, key)
    max_price = min_price*3
    marketplace_asks = fill_dict(min_price, max_price)
    detailed_asks = []
    continuation = None
    total = 0

    store_data = (input("Store ask data in .db file? [Y/n]: ") == "Y")
    verbose = True if not store_data else (input("Output ask data? [Y/n]: ") == "Y")

    # continually fetches the next page of asks and updates the marketplace orders with the next asks
    for i in range(15):
        asks = data.get_open_asks(contract, key, continuation)
        orders = asks["orders"]
        continuation = asks["continuation"]

        parse_asks(orders, marketplace_asks = marketplace_asks, detailed_asks = detailed_asks, min_price = min_price, max_price = max_price)

    marketplace_asks = dict(OrderedDict(sorted(marketplace_asks.items()))) # sort the orderbook by price

    # print out the data in an easily copiable format so that it can be pasted into excel, google sheets, etc and store it in a .db file 
    if verbose:
        print(f"Asks at each round ETH value from {min_price} to {max_price}:")

    for value in marketplace_asks.keys():
        if verbose:
            print(str(value) + ":" + str(marketplace_asks[value]))
        total += marketplace_asks[value]

    if total == len(detailed_asks):
        insert_data(detailed_asks, "ask")

    return detailed_asks

# manage ask distribution
def manage_ask_distribution(bar_chart = True) -> dict:
    asks = manage_asks(verbose = False)
    count = {}

    for ask in asks:
        if ask.marketplace in count.keys():
            count[ask.marketplace] += 1
        else:
            count[ask.marketplace] = 1

    count = {k: v for k, v in sorted(count.items(), key=lambda item: item[1])}

    print(count)

    if bar_chart:
        bar_chart(count)

    return count

# manage bids
def manage_bids() -> None:
    detailed_bids = []
    continuation = None

    # single bids
    for i in range(15):
        single_bids = data.get_looksrare_bids(contract = contract, continuation = continuation)
        try:
            continuation = single_bids[-1]["hash"]
        except:
            continuation = None

        parse_looksrare_bids(single_bids, detailed_bids = detailed_bids)

    # collection bids
    for i in range(15):
        collection_bids = data.get_looksrare_bids(contract = contract, strategy = "0x86F909F70813CdB1Bc733f4D97Dc6b03B8e7E8F3")
        parse_looksrare_bids(collection_bids, detailed_bids = detailed_bids)

    insert_data(detailed_bids, "bid")

# manage trades
def manage_trades(verbose: bool = False, store_data: bool = True) -> None:
    detailed_trades = []
    continuation = None

    store_data = (input("Store trade data in .db file? [Y/n]: ") == "Y")
    verbose = True if not store_data else (input("Output trade data? [Y/n]: ") == "Y")

    for i in range(15):
        trade_data = data.get_trades(contract, key, continuation)
        trades = trade_data["trades"]
        continuation = trade_data["continuation"]

        parse_trades(trades, detailed_trades)

    if store_data:
        insert_data(detailed_trades, "trade")

    if verbose:
        for trade in detailed_trades:
            print(f"Marketplace: {trade.marketplace} \n Project: {trade.project_name} \n Currency: {trade.currency} \n Value: {trade.value} \n Created At: {trade.timestamp} \n")
    

# instance variables
contract = get_contract_address()
target_marketplaces = get_input_names()
data_type = get_data_type()
key = data.get_reservoir_api_key()
token_ids = []

print("fetching data... \n")

# pull and organize ask data
if data_type == "asks":
    manage_asks(verbose = False)

# pull and organize ask distribution data
if data_type == "ask_distribution":
    manage_ask_distribution()

# pull and organize bid data
if data_type == "bids":
    manage_bids()

# pull and organize trade data
if data_type == "trades":
    manage_trades(verbose = True)

print("\ndata parsing complete")
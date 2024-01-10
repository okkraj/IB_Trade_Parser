import sys
import locale
from decimal import Decimal

# IB report is in US format: values are like this 1,000,000.00
locale.setlocale(locale.LC_ALL, 'en_us')

arguments = sys.argv[1:]
if len(arguments) < 1:
    print( "1 args (csv to parse and optionally currency xml) please" )
    sys.exit(1)

csv_file = arguments[0]
currency_xml_file = arguments[1] if len(arguments) > 1 else None
purchases_file = "Purchases.json" 
        
## arguments parsed
## make currency converter
import CurrencyRate
Rate = CurrencyRate.Rate(currency_xml_file)

def GetRates( dict_item ):
    date = GetDate(dict_item['date'])
    rate1 = Rate.GetRate(date, 'EUR', dict_item['currency'])
    rate2 = Rate.GetRate(date, 'EUR', dict_item['comission_currency'])
    
    return rate1, rate2

## Open JSON file for existing trades
import os
import json

def openJson( filename ):
    content = ""
    json_list = []
    if os.path.exists( filename ):
        with open(filename, 'r') as File:
            content = File.read() # used in backup when writing
            json_list = json.loads(content)
            File.close() 
    return json_list, content

purchase_list, file_content = openJson( purchases_file )

# use name of purchase file add .own before final file end
own_file_base = purchases_file.split('.', 1)
own_rule_file = own_file_base[0]+'.own.'+own_file_base[1]
own_rules_list = openJson( own_rule_file )[0] # use only json content, ignore file content
        
###### Date handling
from datetime import datetime
def GetDate( date_str ) :
    return datetime.strptime(date_str, '%Y-%m-%d' ).date()

def GenerateTrade( ticker, quantity, date, currency, price, commcurr, comission, transID ):
    item = { 'ticker' : ticker,
             'pcs' : str(quantity),
             'date' : date,
             'currency' : currency,
             'price' : price,
             'comission' : comission,
             'comission_currency' : commcurr,
             'ID' : transID }
    return item

def CurrencyTrade( ticker ):
    return True if '.' in ticker else False
    
def CheckOwnRules( OwnRules, sell_dict, transID ):
    for i in OwnRules:
        if i['type'] == "spinoff_dividend": # if this type of item, expect certain data in other fields
            if sell_dict['ID'] in i['lookupID']: # sell item ID should be marked into look up
                if sell_dict['ticker'] == i['destination']: # then verify that ticker also matches               
                    return GenerateTrade(sell_dict['ticker'], str(abs(Decimal(sell_dict['pcs']))), i['date'], i['currency'], i['price'], i['comission_currency'], i['comission'], i['ID'] )
        if i['type'] == "split": # if this type of item, expect certain data in other fields
            pass # not processed check here
                            
        # TODO: expand list with other corporate actions...
    return None

def IDexists( DictList, transID ):
    for i in DictList:        
        seek = ('ID', transID)
        if seek in i.items():
            return i 
     
    return None
    
def BoughtSoldBeforeAfter( sell_item, purchase_item, ticker, date):
    ret = False
    if sell_item['ticker'] == ticker and purchase_item['ticker'] == ticker:
        if GetDate(purchase_item['date']) <  GetDate(date) and GetDate(sell_item['date']) >= GetDate(date):
            ret = True
            
    return ret

def GetPurchasePrice( sell_item, purchase_item ):
    price = Decimal(purchase_item['price'])
    return price

def CheckSplits( OwnRules, trade_dict ):
    latest_date = None
    for i in OwnRules:
        if i['type'] == "split":
            if trade_dict['ticker'] == i['ticker']:
                date = trade_dict['date'] if latest_date == None else latest_date                  
                if date < i['date']:                
                    trade_dict['price'] = str( Decimal(trade_dict['price']) * Decimal(i['original']) / Decimal(i['new']) )                  
                    #trade_dict['pcs'] = str( Decimal(trade_dict['pcs']) * Decimal(i['new']) / Decimal(i['original']) )
                    ref_date = i['date']
                    print( f"Found split for {trade_dict['ticker']} at {i['date']} ratio {Decimal(i['original'])} -> {Decimal(i['new'])}" )     
    return trade_dict
    

## go through CSV file
import csv

expected_names = [ 'CurrencyPrimary', 'Symbol', 'Quantity', 'TradePrice', 'TradeDate', 'TransactionID', 'IBCommission', 'IBCommissionCurrency', 'Buy/Sell' ]
idx_currency = 0
idx_symbol = 1
idx_quantity = 2
idx_price = 3
idx_date = 4
idx_id = 5
idx_comission = 6
idx_commcurr = 7

added_trades = 0
sell_list = [] # garther all sells into list

with open(csv_file) as csv_file:
    line_count = 0    

    open_ticker = None
    open_quantity = 0
    sell = [] # gather sell and related purchase(s) to the list
    
    for row in csv.reader(csv_file, delimiter=','):
        if line_count == 0:
            #print(f'Column names are {", ".join(row)}')   
            if row != expected_names:
                raise Exception("Header part names does not match") # sanity check 
        else:
            ticker = row[idx_symbol]
            if CurrencyTrade( ticker ):
                print( f"Skipping currency trade {row}" )
                continue # skip this CSV line               
            quantity = int(row[idx_quantity])
            currency = row[idx_currency]
            price_str = row[idx_price]
            date_str = row[idx_date]
            transID = row[idx_id]
            comission_str = row[idx_comission]
            commcurr = row[idx_commcurr]
            
            if quantity < 0: # sell row
                if open_quantity != 0:
                    raise Exception("Previous quantity not 0") # sanity check
                open_quantity = quantity
                open_ticker = ticker
                trade = GenerateTrade(ticker, quantity, date_str, currency, price_str, commcurr, comission_str, transID )
                sell.append( trade )
            else:
                if open_quantity != 0: # selling
                    if ticker != open_ticker:
                        raise Exception("Ticker not match") # sanity check
                    open_quantity += quantity
                    if open_quantity > 0:
                        raise Exception("Sold too much") # sanity check
                    trade = GenerateTrade(ticker, quantity, date_str, currency, price_str, commcurr, comission_str, transID )
                    sell.append( trade )
                    if open_quantity == 0: # sell & related purchases finished
                        sell_list.append( sell )
                        sell = [] # new empty list
                else:
                    if not CurrencyTrade( ticker ):
                        trade = GenerateTrade(ticker, quantity, date_str, currency, price_str, commcurr, comission_str, transID )
                        
                        exists = IDexists( purchase_list, trade['ID'] )                            
                        if exists is None:
                            purchase_list.append( trade )
                            added_trades += 1
                        else:
                            if trade != exists:
                                raise Exception(f"Transaction ID ({trade['ID']}) already exists") # sanity check    
                    else:
                        print( "skipped currency trade" )

        line_count += 1
    
print( f'found {added_trades} new purchases, total amount is {len(purchase_list)}')

if added_trades > 0:
    # make backup
    import time
    backup_file = purchases_file+'.'+time.strftime("%Y%m%d-%H%M%S")+'.bak'
    
    print( f"\nSaving file: {backup_file}..." )
    with open(backup_file, 'w') as FileBackup:
        FileBackup.write(file_content)
        FileBackup.close()
    # store new file   
    print( f"Saving file: {purchases_file}..." )
    with open(purchases_file, 'w') as File:
      File.write( json.dumps(purchase_list, indent=2) )
      File.close()
    
# seek proper purchases for sell items based on transaction ID  
print("\nMatching sells and related purchases:")
for i in sell_list:
    for j in i:
        if j != i[0]: # not first item
            exists = IDexists( purchase_list, j['ID'] ) # ID could be "" if certain corporate action                       
            if exists is None:
                exists = CheckOwnRules( own_rules_list, i[0], j )
                if exists is None:
                    raise Exception(f"Transaction ID ({j['ID']}) not exists") # sanity check
                else:
                    print( f"Using own purchase rule for trade:\n{i[0]}\n--->{exists}" )
                    
            exists = CheckSplits( own_rules_list, exists )
            j['purchase'] = exists # add new dict item containing original purchase    

# calculate profits
print("\nCalculating profits:")
total_losses = 0
total_profits = 0 
total_purchases = 0
total_sells = 0
for i in sell_list:
    sell_item = i[0]
    sell_price = Decimal(sell_item['price'])
    sell_date = GetDate(sell_item['date'])
    sell_ticker = sell_item['ticker']
    sell_pcs = Decimal(sell_item['pcs'])*-1 # negative value
    sell_curr = sell_item['currency']
    sell_comm = Decimal(sell_item['comission'])
    sell_comm_cur = sell_item['comission_currency']
    
    rate1, rate2 = GetRates( sell_item )    
    sell_eur = ((sell_price/rate1)*sell_pcs) + (sell_comm/rate2) # comission is negative '+' decreases sell price
    #print( f"{sell_ticker} sell rates {rate1} {rate2} pcs {sell_pcs} total: {sell_eur:.2f}" )
    
    buy_eur = 0
    
    for j in i:
        if i.index(j) != 0: # not first (sell) item
            purchase = j['purchase']
            buy_price = GetPurchasePrice( sell_item, purchase )
            buy_date = GetDate(purchase['date'])
            buy_ticker = purchase['ticker']
            buy_pcs = Decimal(j['pcs']) # pcs from 'original' list all others from purchase
            buy_curr = purchase['currency']
            buy_comm = Decimal(purchase['comission'])
            buy_comm_cur = purchase['comission_currency']

            rate1, rate2 = GetRates( purchase )
            buy_e = ((buy_price/rate1)*buy_pcs) + ((-1*buy_comm)/(rate2)) # comission is negative '-1' adds buy price
            buy_eur += buy_e
            #print( f"{buy_ticker} buy rates {rate1} {rate2} pcs{buy_pcs}, line sum {buy_e:.2f} total sum {buy_eur:.2f}" )
            
    profit = sell_eur-buy_eur
    total_purchases += buy_eur
    total_sells += sell_eur
    print( f"{sell_ticker} {sell_date} pcs: {sell_pcs} sell: {sell_eur:.2f} buy: {buy_eur:.2f} profit: {profit:.2f}" )
    
    if profit > 0:
        total_profits += profit
    else:
        total_losses += profit
    
print( f"Profits {total_profits:.2f} EUR, Losses: {total_losses:.2f} EUR, Total {total_profits+total_losses:.2f} EUR" ) # '+' since losses is negative
print( f"Purchase prices total {total_purchases:.2f} EUR, sell prices total: {total_sells:.2f} -> {total_sells-total_purchases:.2f} EUR" )

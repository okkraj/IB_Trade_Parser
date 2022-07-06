import sys
import locale
from decimal import Decimal

# IB report is in US format: values are like this 1,000,000.00
locale.setlocale(locale.LC_ALL, 'en_us')

arguments = sys.argv[1:]
if len(arguments) < 2:
    print( "2 args (csv to parse and currency xml) please" )
    sys.exit(1)

csv_file = arguments[0]
currency_xml_file = arguments[1]

import os
year = os.path.basename(csv_file).split('_')[0]
report_date_str = year+'-12-31'
if len(arguments) == 3:
    report_date_str = arguments[2]

## arguments parsed
## make currency converter
import CurrencyRate
Rate = CurrencyRate.Rate(currency_xml_file)

###### Date handling
from datetime import datetime
def GetDate( date_str ) :
    return datetime.strptime(date_str, '%Y-%m-%d' ).date()

## go through CSV file
import csv

expected_names = [ 'CurrencyPrimary', 'Symbol', 'Quantity', 'PositionValue', 'CostBasisPrice', 'OpenDateTime' ]

print('report date ' + report_date_str)
report_date = GetDate(report_date_str)
  
with open(csv_file) as csv_file:
    line_count = 0
    new_item = False
    
    currency = None
    ticker = None
    count = 0
    position_value = 0
    cost = 0
    
    symbols = []
    new_lines = []
    aq_price = 0
    now_price = 0
    close_price = 0
    
    idx_currency = 0
    idx_ticker = 1
    idx_quantity = 2
    idx_value = 3
    idx_cost = 4
    idx_date = 5
    
    for row in csv.reader(csv_file, delimiter=','):
        if line_count == 0:
            #print(f'Column names are {", ".join(row)}')   
            if row != expected_names:
                raise Exception("Header part names does not match") # sanity check 
        else:            
            if row[idx_date] == '':
                if count != 0:
                    raise Exception("Previous item not fully parsed") # sanity check 
                new_item = False                
                currency = row[idx_currency]
                ticker = row[idx_ticker]
                count = Decimal(row[idx_quantity])
                position_value = Decimal(row[idx_value])
                cost = Decimal(row[idx_cost])
                
                aq_price = 0
                now_price = 0
                rate = Rate.GetRate(report_date, 'EUR-'+currency)
                close_price = Decimal( position_value / count ) / rate
            else:            
                date = GetDate( row[idx_date].split(',')[0] ) # date
                
                if row[idx_currency] != currency:
                    raise Exception("Wrong currency found") # sanity check
                if row[idx_ticker] != ticker:
                    raise Exception("Wrong ticker found") # sanity check
                
                rate = Rate.GetRate(date, 'EUR-'+currency)
                eur_price = Decimal(row[idx_cost]) / rate
                
                amount = Decimal(row[idx_quantity])
                line_aq_price = eur_price * amount
                line_now_price = close_price * amount
                
                aq_price += line_aq_price
                now_price += line_now_price
                
                new_lines.append( [ticker, date, line_aq_price, line_now_price, amount ] )
                
                count -= amount                
                if count < 0:
                    raise Exception("Wrong count found") # sanity check                    
                if count == 0:
                    symbols.append( [ ticker, aq_price, now_price ] )
        line_count += 1
    
    print( 'found ' + str(len(symbols)) + ' different tickers')
    profit = 0
    for i in symbols:
        prof = i[2]-i[1]
        profit += prof
        print( '{0}: {1:.2f} EUR, pending profit: {2:.2f} EUR'.format( i[0], i[1], prof ))
        
    aq_price = sum(i[1] for i in symbols)
    now_price = sum(i[2] for i in symbols)
    print('==> Total Aq: {0:.2f} EUR, now: {1:.2f}, pending profit {2:.2f} EUR'.format( aq_price, now_price, now_price-aq_price))
    
    print( "\nOwn equity (70% rule, using current price if 70% of it is higher than aquisition price):" )
    OPO = 0
    for i in new_lines:
        #print(f"{i[0]}: pcs {i[4]} {i[1]} {i[2]:.2f} {i[3]:.2f} profit {i[3]-i[2]:.2f}")
        now = i[3]*Decimal(0.7)
        aq = i[2]
        OPO += aq if aq > now else now
    
    print('OPO: {0:.2f} EUR'.format(OPO))    
    
    
        
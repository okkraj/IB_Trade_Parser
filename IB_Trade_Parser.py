import sys
from decimal import Decimal
from collections import namedtuple

if len(sys.argv) == 1:  # no args, use example html
    sys.argv = [sys.argv[0], 'example.html']

arguments = sys.argv[1:]
if len(arguments) != 1:
    print( "1 args (html to parse) please" )
    sys.exit(1)

import os
# scriptname without post fix + confif post fix
ConfigFile = os.path.splitext(sys.argv[0])[0]+'_Config.txt' 

import json
with open(ConfigFile, 'r') as File:
    Config = json.loads(File.read())
    File.close()

XmlFile = Config['CurrConvXML']
HtmlFile = arguments[0]

base = Config['BaseCurr'].upper() # currency used in reports

##### =====> all basic stuff checked & set

###### Solve needed currency based on exchange or ticker
def GetCurrency( Ticker, Exchange = None ):
    target = Config['DefaultConvCurr'] # by default use user defined currency
    found = False
    # Prioritize exchange since same ticker can exists in multiple exchanges
    if Exchange is not None:
        for i in Config['Exchanges']:
            if i['Exch'] == Exchange:
                target = target = i['Curr']
                found = True
                break
    if not found:
        for i in Config['UsedCurr']:
            if i['Ticker'] == Ticker:
                target = i['Curr']
                break  
    return (Config['BaseCurr']+'-'+target).upper() # construct nnn-yyy currency pair


###### Currency handling
import xml.etree.ElementTree as ET
root = ET.parse(XmlFile).getroot()

def GetRate(Date, Currency, root) :
    OrigDate = Date
    while OrigDate - Date < timedelta(7): # search max 1 week
        NS = {'ns': 'valuuttakurssit_short_xml_fi' }
        # Look correct date (period) with given currency (rate) and expect it to exr-tag which has "value" field
        for rate in root.iterfind( ".//ns:period[@value='%s']//ns:rate[@name='%s']/ns:exr[@value]" % (Date, Currency.upper()), NS ):
            return Decimal(rate.get('value').replace(',','.'))          
        Date -= timedelta(1) # search into old dates direction
    # Not found
    raise Exception("Currency [{0}] not found near date {1} - ended {2}".format(Currency, OrigDate, Date))

###### Date handling
from datetime import datetime, timedelta
def GetDate( date_str ) :
    return datetime.strptime(date_str, '%Y-%m-%d' ).date()

from dateutil.relativedelta import relativedelta
def GetYearDiff( date1, date2 ):    
    return abs(relativedelta(date1, date2).years)

###### HTML handling
from html.parser import HTMLParser

HtmlLine = namedtuple( 'HTMLTrade', 'Ticker Date QTY Price Fee Exchange' )

class MyHTMLParser(HTMLParser):
    
    def __init__(self):
        HTMLParser.__init__(self,)
        self.tr = False # 'tr'-tag found in html
        self.sell = False # 'row-summary' text found in html
        self.buy = False # 'closed-slot' text found in html
        self.tdcnt = 0
        self.trades = [] # list of lists
        self.trade = [] # single sell, possible multiple purhaces to fill it
        self.temp = ()
        self.Fee = 0
        self.Linesfound = 0
        self.exchange = None

    def ProcessLine(self, Sell):
        self.Linesfound += 1
        if Sell and self.trade: # list should be empty at this phase
            raise Exception("New sell but list not empty")
        if not Sell and not self.trade: # list should have at least sell row at this phase
            raise Exception("New buy but list empty")
        if Sell and self.company is None:
            raise Exception("Company parsing failed") # sanity check        
        row = HtmlLine( Ticker=self.company if Sell else self.trade[0].Ticker,
                        Date=self.temp[0], QTY=self.temp[1], Price=self.temp[2], Fee=self.Fee,
                        Exchange=self.exchange if Sell else self.trade[0].Exchange )        
        if (Sell and row.QTY >= 0) or (not Sell and row.QTY <= 0):
            raise Exception("QTY is invalid") # sanity check 
        self.trade.append( row )
        print( '{0.Ticker}, {0.Date}, {0.QTY}, {0.Price}, {0.Fee}, {0.Exchange}'.format(row) )
        for i in self.trade:
            QTY = i.QTY if i is self.trade[0] else QTY + i.QTY # Decrease buys from sell (sell is negative so this goes towards zero)
            if QTY == 0: # all buy rows found -> 1 Sell trade completely processed       
                self.trades.append( self.trade )
                self.trade = [] # not using .clear(), create new object instead to preserve old list in list of lists
                print( '='*40 )
    
    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.tr = True
            self.tdcnt = 0
            if len(attrs) > 0:
                i=attrs[0]
                if i[0] == "class":
                    if i[1] == "row-summary":
                        self.sell = True # could be also splitted purchase, need to read td's to determine it
        if tag == "td":
            self.tdcnt += 1

    def handle_endtag(self, tag):
        if tag == "tr":
            if self.sell and self.buy:
                raise Exception("sell and buy both enabled") # sanity check 
            if self.sell or self.buy:                
                self.ProcessLine(True if self.sell else False)
            self.tr, self.sell, self.buy = False, False, False
            self.temp = () # clear for next line, clear here since some data may have been collected
            self.company = None # cannot be none
            self.exchange = None # can be none

    def handle_data(self, data):
        if not data.strip():
            return
        if self.tdcnt == 1:
            if data == "Closed Lot:":
                self.buy = True;
            if self.sell:
                self.company = data # only in sell line
        if self.tdcnt == 3 and self.sell:
            self.exchange = data # only in sell line
        if self.sell or self.buy:
            if self.tdcnt == 2:
                self.temp += (GetDate( data.split(',')[0] ), ) # date
            if self.tdcnt == 4:
                if self.sell and Decimal(data) >= 0: # this is actually purchase which has been splitted
                    self.sell = False
                self.temp += (Decimal(data), ) # QTY, there can be at least 0.5, sell has negative
            if self.tdcnt == 5:
                self.temp += (Decimal(data), ) # Price
            if self.tdcnt == 7:
                self.Fee = abs(Decimal(data)) # Comission/Fee (only in sell line) --- negative in HTML!!!
                
##################END OF CLASS #################################                
TradeSqueeze = namedtuple( 'SqueezedTrade', 'Ticker Date QTY TotalSell TotalBuy Profit SellFees BuyFees Currency' )

def CalculateProfit( TradeList ): # input: list of 'HtmlLine'-lists, output: list of 'TradeSqueeze'
    ProfitList = []
    
    for trade in TradeList:
        BuyFees = Decimal(0)
        SellValue = Decimal(0)
        BuyValue = Decimal(0)
        SellSingleBase = Decimal(0)
        for i in trade: # squeeze closed slots into one (1 sell & 1 buy )
            Currency = GetCurrency(i.Ticker)
            SingleBase = i.Price/GetRate(i.Date, Currency, root) # 1 QTY in Base
            valueBase = SingleBase*abs(i.QTY) # make all positive despite of QTY
            if i.QTY < 0: # selling
                SellValue = valueBase # store
                SellSingleBase = SingleBase
                BuyValue = Decimal(0) # reset here
                SellFee = i.Fee # if using hankintameno-olettama, line part of sell fee needs to be substracted from this
                PartialSellFee = Decimal(i.Fee/(len(trade)-1)) # -1 == this sell item, residual: part of this buy line from all buy lines 
            else:   # buying
                BuyFees += i.Fee # sum buy fees
                valueBase += i.Fee # add fee for this buy slot to minimize profit                
                SlotSell = SellSingleBase*abs(i.QTY) # no fee here, "hankintameno" cannot use it
                if (SlotSell-PartialSellFee) > (valueBase): # Making profit with fee's, consider "hankintameno"                
                    # Calculate "hankintameno"
                    Diff = GetYearDiff(i.Date, trade[0].Date)
                    Percentage = Decimal(Config['HankintamenoBasic']) if Diff < Config['HankintamenoYears'] else Decimal(Config['HankintamenoExt'])
                    HankintaMeno = SlotSell*Percentage                    
                    # Hankintameno: pure_sell*percentage > buy+its fee+selling fee
                    if HankintaMeno > (valueBase+PartialSellFee): # Use hankintameno if bigger -> less profit for taxing  
                        valueBase = HankintaMeno # replace buy price with hankintameno price
                        # with hankintameno cannot substract fee's remove those from both buy & sell
                        BuyFees -= i.Fee # remove initially added purchase fee for this slot
                        SellFee -= PartialSellFee # substract this line's part from the sell fee
                BuyValue += valueBase # Finally set this slot "purchase price"

        SellValue = (SellValue - SellFee) if SellValue > SellFee else Decimal(0) # substact fee to minimize profit
        # After squeeze - Store trade summary (i.e. 1 trade with same QTY buy&sell)
        x = TradeSqueeze( Ticker=trade[0].Ticker, Date=trade[0].Date, QTY=abs(trade[0].QTY),
                          TotalSell=SellValue, TotalBuy=BuyValue, Profit=abs(SellValue)-BuyValue,
                          SellFees=SellFee, BuyFees=BuyFees, Currency = Currency)
        ProfitList.append( x )

    return ProfitList
######################################################

with open(HtmlFile, 'r') as myfile:
  HTMLdata = myfile.read()
  myfile.close()
 
parser = MyHTMLParser()
parser.feed(HTMLdata)
print( "Found:", len(parser.trades), "trades, in", parser.Linesfound, "Lines. Squeezing trades to one liners..." )

List = CalculateProfit( parser.trades )

######## All done - just print the content out ########

print( 40*'=', '\n'+str(List[0]._fields) ) # print tuple field names
for i in List:  
    print( '{0.Ticker}, {0.Date}, {0.QTY}QTY, {0.TotalSell:.2f}{1}, {0.TotalBuy:.2f}{1}, {0.Profit:.2f}{1}, {0.SellFees:.2f}{1}, {0.BuyFees:.2f}{1}, {0.Currency}'.format(i, base) )

print( 40*'=', "\nCombining trades to one:" )
TotalSell = sum([i.TotalSell for i in List])
TotalBuy = sum([i.TotalBuy for i in List])
ProfitCheck = sum([i.Profit for i in List])
TotalFees = sum([i.SellFees for i in List]) + sum([i.BuyFees for i in List])

Profit = abs(TotalSell)-TotalBuy
print( "TotalSell: {1:.2f}{0}, TotalBuy: {2:.2f}{0}, Profit: {3:.2f}{0}".format(base, TotalSell, TotalBuy, Profit) )
if round(Profit,2) != round(ProfitCheck,2):
    raise Exception("Profit check failed!!! {} != {}".format(Profit, ProfitCheck))
print( 40*'=' )
print( "Info about fees... Total: {1:.2f}{0}, -> {2:.2f}{0} per line".format( base, TotalFees, TotalFees/parser.Linesfound) )

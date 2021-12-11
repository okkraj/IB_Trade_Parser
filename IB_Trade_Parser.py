import sys
import locale
from decimal import Decimal
from collections import namedtuple

# IB report is in US format: values are like this 1,000,000.00
locale.setlocale(locale.LC_ALL, 'en_us')

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
# Get all similar pattern XMLs
XmlFiles = XmlFile.split('.', 1)
ending = '.' + XmlFiles[1]
XmlFiles = XmlFiles[0]
import glob
XmlFiles = glob.glob( './' + XmlFiles + '*' + ending )
roots = []
for i in XmlFiles:
    roots.append( ET.parse(i).getroot() )

def GetRate(Date, Currency, roots) :
    OrigDate = Date
    for root in roots: # go through all XML's
        Date = OrigDate
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
                        Date=self.temp[0], QTY=self.temp[1], Price=self.temp[2], Fee=self.Fee, # if buy row, the fee is in Price itself
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
            self.Fee = 0
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
                data = locale.atof(data, Decimal) # for some reason with this value 3,800 throws an error (perhaps because there is no '.' like 3,800.00)
                if self.sell and Decimal(data) >= 0: # this is actually purchase which has been splitted
                    self.sell = False
                self.temp += (Decimal(data), ) # QTY, there can be at least 0.5, sell has negative
            if self.tdcnt == 5:
                self.temp += (Decimal(data), ) # Price
            if self.tdcnt == 7:
                self.Fee = abs(Decimal(data)) # Comission/Fee (only in sell line) --- negative in HTML!!!
                
##################END OF CLASS #################################                
TradeBase = namedtuple( 'Trades', 'Ticker SellDate BuyDate QTY SellPrice BuyPrice SellFee BuyFee Currency' )

def SplitHtmlToTradesAsBase( TradeList ):
    TradelistAsBase = []
    for trade in TradeList:
        TradeBaseList = []
        QTY = 0
        SellBase = Decimal(0)
        SellDate = ""
        SellFeeBase = Decimal(0)
        CurrencyUsed = ""
        for i in trade:
            Currency = GetCurrency(i.Ticker)
            rate = GetRate(i.Date, Currency, roots)
            SingleBase = i.Price/rate # 1 QTY in Base
            valueBase = SingleBase*abs(i.QTY) # make all positive despite of QTY
            feeBase = i.Fee/rate # fee as base currency (for buy lines, the fee is 0 and included in i.Price)
            if i.QTY < 0: # selling
                QTY = i.QTY # negative
                Trade = [] # reset, but not with .clear to preserve previous instance
                CurrencyUsed = Currency
                SellBase = SingleBase # 1 stock price
                SellFeeBase = feeBase
                SellDate = i.Date
            else:   # buying
                QTY = QTY + i.QTY
                if QTY > 0:
                    raise Exception("QTY is invalid") # sanity check
                if Currency != CurrencyUsed:
                    raise Exception("Wrong currency") # sanity check
                PartOfSellFee = Decimal(SellFeeBase/(len(trade)-1))
                RowInBase = TradeBase( Ticker=i.Ticker, SellDate=SellDate, BuyDate=i.Date, QTY=abs(i.QTY),
                                     SellPrice=SellBase*abs(i.QTY), BuyPrice=valueBase,
                                     SellFee=PartOfSellFee, BuyFee=feeBase, Currency=CurrencyUsed )                
                TradeBaseList.append( RowInBase ) # append to list
                
        TradelistAsBase.append( TradeBaseList ) # append list to list -> list of lists
    return TradelistAsBase

def HankintaMeno( BaseSell, BuyDate, SellDate ):             
    # Calculate "hankintameno"
    Diff = GetYearDiff(BuyDate, SellDate)
    Percentage = Decimal(Config['HankintamenoBasic']) if Diff < Config['HankintamenoYears'] else Decimal(Config['HankintamenoExt'])
    return Decimal(BaseSell*Percentage)                    

def CalcProfit( ProfitBase ):
    # Hankintameno: no fees can be applied
    HankintamenoProfit = ProfitBase.SellPrice - HankintaMeno( ProfitBase.SellPrice, ProfitBase.BuyDate, ProfitBase.SellDate )
    RegularProfit = (ProfitBase.SellPrice-ProfitBase.SellFee)-(ProfitBase.BuyPrice+ProfitBase.BuyFee)

    Profit = RegularProfit
    
    UsingHankintaMeno = False;
    if RegularProfit > 0:   # making money, check if hankintameno is better
        if HankintamenoProfit < RegularProfit:
            Profit = HankProfit
            UsingHankintaMeno = True;
        
    return Profit, UsingHankintaMeno

TradeSqueeze = namedtuple( 'SqueezedTrade', 'Ticker Date QTY TotalSell TotalBuy Profit SellFees BuyFees Currency' )

def squeezeTrade( SqueezeList ):
    if not SqueezeList:
        raise Exception("List is empty") # sanity check

    tot_QTY = sum(i.QTY for i in SqueezeList)
    tot_Sell = sum(i.TotalSell for i in SqueezeList)
    tot_Buy = sum(i.TotalBuy for i in SqueezeList)
    tot_SellFee = sum(i.SellFees for i in SqueezeList)
    tot_BuyFee = sum(i.BuyFees for i in SqueezeList)
    tot_Profit = sum(i.Profit for i in SqueezeList)

    x = TradeSqueeze( Ticker=SqueezeList[0].Ticker, Date=SqueezeList[0].Date, QTY=tot_QTY,
                      TotalSell=tot_Sell, TotalBuy=tot_Buy, Profit=tot_Profit,
                      SellFees=tot_SellFee, BuyFees=tot_BuyFee, Currency = SqueezeList[0].Currency)

    return x  

def CalculateProfitInBase( BaseTradelist ):
    ProfitList = []

    for trade in BaseTradelist:
        TradeProfit = []
        TradeLoss = []
        for i in trade: # divide closed slots into profit and loss lines
            NetProfit, hankmeno = CalcProfit( i )

            x = TradeSqueeze( Ticker=i.Ticker, Date=i.SellDate, QTY=i.QTY,
                              TotalSell=i.SellPrice, TotalBuy=i.BuyPrice, Profit=NetProfit,
                              SellFees=i.SellFee if not hankmeno else Decimal(0), BuyFees=i.BuyFee if not hankmeno else Decimal(0), Currency = i.Currency)
            if hankmeno:
                print( 'Hankintameno used: {0.Ticker}, {0.Date}, {0.QTY}QTY, {0.TotalSell:.2f}{1}, {0.TotalBuy:.2f}{1},{0.Profit:.2f}{1}, {0.SellFees:.2f}{1}, {0.BuyFees:.2f}{1}, {0.Currency}'.format(x, base) )
            if x.Profit >= 0:                
                TradeProfit.append( x )
            else:
                TradeLoss.append( x )

        # squeeze profits and losses to one liners per trade
        if TradeProfit:
            ProfitList.append( squeezeTrade( TradeProfit ) )
        if TradeLoss:
            ProfitList.append( squeezeTrade( TradeLoss ) )
            
    return ProfitList
    
######################################################

with open(HtmlFile, 'r') as myfile:
  HTMLdata = myfile.read()
  myfile.close()
 
parser = MyHTMLParser()
parser.feed(HTMLdata)
print( "Found:", len(parser.trades), "trades, in", parser.Linesfound, "Lines. Generating trades in base currency..." )

TradesAsBase = SplitHtmlToTradesAsBase( parser.trades )
print( 40*'=', "\nList of trades in base currency:", '\n'+str(TradesAsBase[0][0]._fields), "\n", 40*'=' )
for trade in TradesAsBase:
    for i in trade:
        print( '{0.Ticker}, {0.SellDate}, {0.BuyDate}, {0.QTY}, {0.SellPrice:.2f}{1}, {0.BuyPrice:.2f}{1}, {0.SellFee:.2f}{1}, {0.BuyFee:.2f}{1}, {0.Currency}'.format(i, base) )
    print( 40*'=' )

print( "Squeezing trades to one liners..." )
List = CalculateProfitInBase( TradesAsBase )

######## All done - just print the content out ########

print( 40*'=', '\n'+str(List[0]._fields) ) # print tuple field names
for i in List:  
    print( '{0.Ticker}, {0.Date}, {0.QTY}QTY, {0.TotalSell:.2f}{1}, {0.TotalBuy:.2f}{1}, {0.Profit:.2f}{1}, {0.SellFees:.2f}{1}, {0.BuyFees:.2f}{1}, {0.Currency}'.format(i, base) )

## Generate single profit and single loss line of content
SqueezedProfitLine = namedtuple( 'ProfitLine', 'Profit Sell Buy SellFee BuyFee' )
def SeparateList( List, CheckProfit ):
    Separated = []
    for i in List:
        process = False
        if CheckProfit:
            if i.Profit > 0:
                process = True
        else:
            if i.Profit < 0:
                process = True

        if process:
            Separated.append(i)
    
    return SqueezedProfitLine( Profit =sum([i.Profit for i in Separated]),
                               Sell   =sum([i.TotalSell for i in Separated]),
                               Buy    =sum([i.TotalBuy for i in Separated]),
                               SellFee=sum([i.SellFees for i in Separated]),
                               BuyFee =sum([i.BuyFees for i in Separated]) )          

def GetProfit( List ):
    return SeparateList( List, True ) 

def GetLoss( List ):
    return SeparateList( List, False )    

print( 40*'=', "\nCombining trades to one profit and one loss line:" )
Profit = GetProfit( List )
Loss = GetLoss( List )

print( "Profits: TotalSell: {1:.2f}{0}, TotalBuy: {2:.2f}{0}, Profit: {3:.2f}{0}".format(base, Profit.Sell, Profit.Buy, Profit.Profit) )
print( "Losses:  TotalSell: {1:.2f}{0}, TotalBuy: {2:.2f}{0}, Profit: {3:.2f}{0}".format(base, Loss.Sell, Loss.Buy, Loss.Profit) )

# check profit calculations
P_check = Profit.Sell-(Profit.SellFee + Profit.Buy + Profit.BuyFee)
L_check = Loss.Sell-(Loss.SellFee + Loss.Buy + Loss.BuyFee)

if round(Profit.Profit,2) != round(P_check,2):
    raise Exception("Profit check failed!!! {} != {}".format(P_Profit, P_check))
if round(Loss.Profit,2) != round(L_check,2):
    raise Exception("Profit check failed!!! {} != {}".format(L_Profit, L_check))

TotalFees = sum([i.SellFees for i in List]) + sum([i.BuyFees for i in List])
print( 40*'=' )
print( "Info about fees... Total: {1:.2f}{0}, -> {2:.2f}{0} per line".format( base, TotalFees, TotalFees/parser.Linesfound) )

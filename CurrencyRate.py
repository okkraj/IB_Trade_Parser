import sys
import locale
from decimal import Decimal
from datetime import timedelta

import xml.etree.ElementTree as ET
import glob

#from forex_python.converter import CurrencyRates

import requests

class Rate():
    def __init__(self, XmlFile=None):
        self.c = None
        if XmlFile is not None:
            # Get all similar pattern XMLs
            XmlFiles = XmlFile.split('.', 1)
            ending = '.' + XmlFiles[1]
            XmlFiles = XmlFiles[0]
            XmlFiles = glob.glob( './' + XmlFiles + '*' + ending )
            if len(XmlFiles) == 0:
                raise Exception("No XML files found") # sanity check
            self.roots = []
            for i in XmlFiles:
                self.roots.append( ET.parse(i).getroot() )
        else:
            #self.c = CurrencyRates() # not working properly, won't give for example ILS rate
            
            print( "Downloading currencies from suomenpankki.fi..." )
            URL = "https://www.suomenpankki.fi/WebForms/ReportViewerPage.aspx?report=/tilastot/valuuttakurssit/valuuttakurssit_short_xml_fi&output=xml"
            response = requests.get(URL)
            open("latest_currencies.xml", "wb").write(response.content)
            self.roots = ET.parse("latest_currencies.xml").getroot()
            
            
    def GetRate(self, Date, DestCurrency, SrcCurrency=None ) :
        Currency = DestCurrency
        if SrcCurrency is not None:
            Currency = DestCurrency+'-'+SrcCurrency
            
        OrigDate = Date
        
        if self.c is not None:
            Src = Currency.split('-')[0]
            Dest = Currency.split('-')[1]
            while OrigDate - Date < timedelta(7): # search max 1 week
                try:
                    rate = self.c.get_rate( Src, Dest, Date )                    
                except:
                    Date -= timedelta(1) # search into old dates direction
                    raise
                else:
                    return Decimal(rate);
        else:        
            for root in self.roots: # go through all XML's
                Date = OrigDate
                while OrigDate - Date < timedelta(7): # search max 1 week
                    NS = {'ns': 'valuuttakurssit_short_xml_fi' }
                    # Look correct date (period) with given currency (rate) and expect it to exr-tag which has "value" field
                    for rate in root.iterfind( ".//ns:period[@value='%s']//ns:rate[@name='%s']/ns:exr[@value]" % (Date, Currency.upper()), NS ):
                        return Decimal(rate.get('value').replace(',','.'))
                    Date -= timedelta(1) # search into old dates direction
            # Not found
        raise Exception("Currency [{0}] not found near date {1} - ended {2}".format(Currency, OrigDate, Date))

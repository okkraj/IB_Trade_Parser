import sys
import locale
from decimal import Decimal
from datetime import timedelta

import xml.etree.ElementTree as ET
import glob

class Rate():
    def __init__(self, XmlFile):
        # Get all similar pattern XMLs
        XmlFiles = XmlFile.split('.', 1)
        ending = '.' + XmlFiles[1]
        XmlFiles = XmlFiles[0]
        XmlFiles = glob.glob( './' + XmlFiles + '*' + ending )
        self.roots = []
        for i in XmlFiles:
            self.roots.append( ET.parse(i).getroot() )
            
    def GetRate(self, Date, Currency) :
        OrigDate = Date
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

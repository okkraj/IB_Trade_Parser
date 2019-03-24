# IB_Trade_Parser
Script parses Interactive Brokers trade report to aid in Finnish tax report fill

1. Download currency conversion XML from: https://www.suomenpankki.fi/fi/Tilastot/valuuttakurssit/taulukot/
- https://www.suomenpankki.fi/WebForms/ReportViewerPage.aspx?report=/tilastot/valuuttakurssit/valuuttakurssit_short_xml_fi&output=xml
- https://www.suomenpankki.fi/WebForms/ReportViewerPage.aspx?report=/tilastot/valuuttakurssit/valuuttakurssit_long_xml_fi&output=xml

2. Finetune config file to suit your needs

3. Generate custom Interactive Brokers acticity statement with "trades"-option in html format

4. Give you html file as an argument

5. Verify script output, change currencies in config if needed

6. Insert last line summary into your tax report as an one big trade (inogre hankintameno-olettama if suggested) - use imaginary dates...

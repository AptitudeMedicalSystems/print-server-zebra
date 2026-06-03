;; @label width=50.8mm height=50.8mm
;; @field title: str default=ZD411 "Reverse-video header text"
;; @field barcode: str default=TEST12345 "Code128 value, also printed as text"
;; @field qr: str default=QA,https://zebra.test/zd411 "QR code payload"
^XA
^PW406
^LL406
^LH0,0
^CI28
^PR4
^MD10

^FO0,0^GB406,406,2^FS

^FO10,10^GB386,30,30^FS
^FO15,15^A0N,24,24^FR^FD{{title}} TEST^FS

^FO10,50^A0N,18,18^FDFont 18^FS
^FO10,72^A0N,24,24^FDFont 24^FS
^FO10,100^A0N,32,32^FDFont 32^FS

^FO10,140^BY2,2,50^BCN,50,N,N,N^FD{{barcode}}^FS
^FO10,195^A0N,18,18^FD{{barcode}}^FS

^FO10,220^BQN,2,4^FD{{qr}}^FS

^FO180,220^A0N,18,18^FD203 dpi^FS
^FO180,242^A0N,18,18^FD2 x 2 inch^FS
^FO180,264^A0N,18,18^FD406 x 406 dot^FS
^FO180,286^A0N,18,18^FDDarkness 10^FS
^FO180,308^A0N,18,18^FDSpeed 4 ips^FS

^FO10,350^GB386,2,2^FS
^FO10,360^A0N,18,18^FD|....+....1....+....2^FS
^FO10,382^A0N,18,18^FD0123456789ABCDEFGHIJ^FS

^XZ

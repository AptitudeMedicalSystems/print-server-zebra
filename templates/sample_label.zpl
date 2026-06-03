;; @label width=50mm height=30mm
;; @field title: str required "Top line"
;; @field code: str required "Barcode value"
;; @field note: str "Optional note line"
^XA
^CI28
^PW400
^LL240
^LH0,0
^FO20,15^A0N,30,30^FD{{title}}^FS
^FO20,55^A0N,22,22^FD{{note}}^FS
^FO20,95^BCN,90,Y,N,N^FD{{code}}^FS
^XZ

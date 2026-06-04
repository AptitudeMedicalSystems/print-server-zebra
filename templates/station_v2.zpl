;; @label width=57.15mm height=50.8mm
;; @field sn: str required "Serial number (e.g. S201135Q000004)"
;; @field duid: str required "Device UID (16-digit)"
;; @field mid_line1: str required "MID first half (~18 chars)"
;; @field mid_line2: str required "MID second half (~17 chars)"
;; @field timestamp: str required "e.g. 2026-06-03 17:29 UTC"
;; @field url: str required "Device URL"
^XA
^PW456
^LL406
^LH0,0
^CI28
^FO20,20^A0N,28,28^FDStation V2^FS
^FO20,55^GB420,2,2^FS
^FO20,70^A0N,22,22^FDSN^FS
^FO20,95^A0N,30,30^FD{{sn}}^FS
^FO20,135^BY2,2,60^BCN,60,N,N,N^FD{{sn}}^FS
^FO20,210^A0N,20,20^FDDUID^FS
^FO20,232^A0N,24,24^FD{{duid}}^FS
^FO20,270^A0N,18,18^FDMID {{mid_line1}}^FS
^FO20,292^A0N,18,18^FD     {{mid_line2}}^FS
^FO20,330^GB420,2,2^FS
^FO20,345^A0N,18,18^FD{{timestamp}}^FS
^FO20,367^A0N,18,18^FD{{url}}^FS
^XZ

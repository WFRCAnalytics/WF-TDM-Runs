;System
    ;file to halt the model run if model crashes
    *(ECHO 'model crashed' > redistribute_hbw_trips.txt)



;get start time
ScriptStartTime = currenttime()



;====================================================================================================================================================================;
;Python HBW Trip Redistribution (bring-work-trips-closer-to-home)
;====================================================================================================================================================================;

; redistribute a share of HBW trips from each origin zone toward destinations
; within that zone's own geography unit -- hbw_trip_redistribution_portion /
; geography_type are read directly by the python script from the scenario's
; own CloseXX.yaml `variables:` block (they are not Control Center keys, so
; Cube itself never sees them; only @ScenarioName@/@ScenarioDir@/@ModelDir@
; are passed through here)
;  note using single asterix minimizes the command window when executed, double asterix executes the command window non-minimized
;  note: the 1>&2 echos the python window output to the one started by Cube
**"@ModelDir@\2_ModelScripts\_Python\py-tdm-env\python.exe" "@ModelDir@\..\run_sets\bring-work-trips-closer-to-home\scripts\redistribute_hbw_trips.py" --run-set-dir "@ModelDir@\..\run_sets\bring-work-trips-closer-to-home" --scenario-id "@ScenarioName@" --input-mtx "@ScenarioDir@\Temp\4_ModeChoice\pa_AllPurp.2.DestChoice.mtx" --taz-dbf "@ModelDir@\1_Inputs\1_TAZ\WFv1000_TAZ.dbf" 1>&2


;handle python script errors
if (ReturnCode<>0)

    PROMPT QUESTION='Python failed to run correctly',
        ANSWER="Please check the console output above for error messages."

    GOTO :ONERROR

    ABORT

endif  ;ReturnCode<>0


;DOS command to delete '__pycache__' folder
;  note: '/s' removes folder & contents of folder includling any subfolders
;  note: '/q' denotes quite mode, meaning doesn't ask for confirmation to delete
*(rmdir /s /q "@ModelDir@\..\run_sets\bring-work-trips-closer-to-home\scripts\__pycache__")




;print timestamp
RUN PGM=MATRIX

    ZONES = 1

    ScriptEndTime = currenttime()
    ScriptRunTime = ScriptEndTime - @ScriptStartTime@

    PRINT FILE='@ScenarioDir@\_Log\_RunTime.txt',
        APPEND=T,
        LIST='\n    HBW Trip Redistribution            ', formatdatetime(@ScriptStartTime@, 40, 0, 'yyyy-mm-dd,  hh:nn:ss'),
                 ',  ', formatdatetime(ScriptRunTime, 40, 0, 'hhh:nn:ss')

ENDRUN




*(del redistribute_hbw_trips.txt)

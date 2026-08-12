;System
    ;file to halt the model run if model crashes
    *(ECHO 'model crashed' > shift_hbw_trip_length.txt)



;get start time
ScriptStartTime = currenttime()



;====================================================================================================================================================================;
;Python HBW Trip-Length Shift (shorten-lengthen-all-work-trips)
;====================================================================================================================================================================;

; shifts every origin zone's own trip-volume-weighted mean HBW commute
; distance by hbw_trip_length_shift_pct, reweighting only that origin's
; existing destination pattern (favoring closer destinations to shorten,
; farther ones to lengthen) -- applied to 100% of origins with existing HBW
; trips, not a selected subset. hbw_trip_length_shift_pct is read directly
; by the python script from the scenario's own ShiftXX.yaml `variables:`
; block (not a Control Center key, so Cube itself never sees it; only
; @ScenarioName@/@ScenarioDir@/@ModelDir@ are passed through here)
;
; Edits pa_HBW_NumVeh_noXI.mtx's HBW0/HBW1/HBW2 cores -- the file
; 08_TripTablesByPeriod.s actually reads forward into mode choice/assignment
; -- not pa_AllPurp.2.DestChoice.mtx's aggregate HBW core (see
; bring-work-trips-closer-to-home/scripts/redistribute_hbw_trips.py's module
; docstring for why). pa_AllPurp.2.DestChoice.mtx is still passed through so
; its own HBW core can be kept in sync for P/A-balance reporting.
;
; Distance basis is skm_auto_Pk.mtx's dist_GP core -- already produced by
; 03_Skim_auto.s during Closer00's original run and carried into this
; scenario's folder via start_from_copy, same as pa_HBW_NumVeh_noXI.mtx
; itself.
;  note using single asterix minimizes the command window when executed, double asterix executes the command window non-minimized
;  note: the 1>&2 echos the python window output to the one started by Cube
**"@ModelDir@\2_ModelScripts\_Python\py-tdm-env\python.exe" "@ModelDir@\..\run_sets\shorten-lengthen-all-work-trips\scripts\shift_hbw_trip_length.py" --run-set-dir "@ModelDir@\..\run_sets\shorten-lengthen-all-work-trips" --scenario-id "@ScenarioName@" --numveh-mtx "@ScenarioDir@\Temp\4_ModeChoice\pa_HBW_NumVeh_noXI.mtx" --destchoice-mtx "@ScenarioDir@\Temp\4_ModeChoice\pa_AllPurp.2.DestChoice.mtx" --skim-mtx "@ScenarioDir@\4_ModeChoice\1a_Skims\skm_auto_Pk.mtx" 1>&2


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
*(rmdir /s /q "@ModelDir@\..\run_sets\shorten-lengthen-all-work-trips\scripts\__pycache__")




;print timestamp
RUN PGM=MATRIX

    ZONES = 1

    ScriptEndTime = currenttime()
    ScriptRunTime = ScriptEndTime - @ScriptStartTime@

    PRINT FILE='@ScenarioDir@\_Log\_RunTime.txt',
        APPEND=T,
        LIST='\n    HBW Trip-Length Shift     ', formatdatetime(@ScriptStartTime@, 40, 0, 'yyyy-mm-dd,  hh:nn:ss'),
                 ',  ', formatdatetime(ScriptRunTime, 40, 0, 'hhh:nn:ss')

ENDRUN




*(del shift_hbw_trip_length.txt)

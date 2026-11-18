;==============================================================================
;                   Hail Mary Run Script -- TDM2MOVES VMT Factors Only
;==============================================================================
; This scenario's raw folder is seeded (start_from_copy) from an
; already-completed run's raw scenario folder -- see
; run_sets/tdm-2-moves-factors/scenarios/v10.0-beta.2-2023.yaml. Every
; upstream step (input processing through final highway assignment) is
; reused as-is from that copy; only the one post-processing step below runs.

:BEGINMODEL
    ModelStep = 'BEGIN MODEL'
    ModelStartTime = currenttime() ;get timestamp

    ;initialize by reading in scenario general and specific parameters
    READ FILE = '_ControlCenter.block'
    READ FILE = '..\..\..\1_Inputs\0_GlobalData\GeneralParameters.block'

    ;set on error goto parameter (set label to jump to if an error occurs)
    ONRUNERRORGOTO='ONERROR'

    ;delete old prn files
    *(DEL *.PRN)

:STEP7
    ModelStep = 'STEP 7 - TDM2MOVES VMT Factors'
    BegTime_PP = currenttime() ;get timestamp

    READ FILE = '..\..\..\..\run_sets\tdm-2-moves-factors\hail-mary\01_Calculate_Factors_VMT.s'

    READ FILE = '..\..\..\2_ModelScripts\7_PostProcessing\_TimeStamp_PP.block' ;report model step run time

:ENDMODEL
    READ FILE = '..\..\..\2_ModelScripts\_TimeStamp_ModelSuccess.block' ;report model step run time

    Exit ;quit model run

;if an error occurs the process jumps to this location
:ONERROR
    READ FILE = '..\..\..\2_ModelScripts\_TimeStamp_ModelCrashed.block' ;report model step run time

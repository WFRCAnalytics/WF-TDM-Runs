

; export loaded summary dbf
RUN PGM=NETWORK MSG='export loaded summary dbf'

    FILEI LINKI[1] = '@ScenarioDir@\5_AssignHwy\2a_Networks\@runId@Summary.net'

    FILEO LINKO =    '@ScenarioDir@\7_PostProcessing\5_TDM2MOVES_Prep\@runId@_Assigned_Summary.dbf'

    ZONES = @UsedZones@

ENDRUN


RUN PGM=MATRIX MSG='Compute AWDT Seasonal Factors using Python'

FILEO PRINTO = '@ScenarioDir_Py@\_Log\py_Variables - pp_Compute_AWDT_Seasonal_Factors.txt'

    ;set parameters
    ZONES = 1

    ;create control input file for this Python script
    PRINT PRINTO=1,
        LIST='# ------------------------------------------------------------------------------',
             '\n# Python input file variables and paths',
             '\n# ------------------------------------------------------------------------------',
             '\n',
             '\n# global parameters ------------------------------------------------------------',
             '\nModelDir_Py      = @ModelDir_Py@',
             '\nScenarioDir_Py   = @ScenarioDir_Py@',
             '\nrunId            = @runId@',
             '\nLoadedLink_dbf   = @ScenarioDir_Py@\7_PostProcessing\5_TDM2MOVES_Prep\@runId@_Assigned_Summary.dbf',
             '\nMasterLink_shp   = @ModelDir_Py@\1_Inputs\3_Highway\@MasterLinkShp@',
             '\nSegmentSeasonshp = @ModelDir_Py@\1_Inputs\6_Segment',
             '\nFactorTables_csv = @ModelDir_Py@\1_Inputs\6_Segment\Factor_Geographies\FactorTables.csv',
             '\nOutfolder        = @ScenarioDir_Py@\7_PostProcessing\5_TDM2MOVES_Prep',
             '\n'

ENDRUN


;run python script -------------------------------------------------------------
;  note: one asterix minimizes the command window, two asterix executes the command window non-minimized
;  note: the 1>&2 echos the command window output from pyton to the one started by Cube
**"@ModelDir@\2_ModelScripts\_Python\py-tdm-env\python.exe" "@ModelDir@\2_ModelScripts\_Python\pp_Compute_AWDT_Seasonal_Factors.py" 1>&2


;handle python script errors
if (ReturnCode<>0)

    PROMPT QUESTION='Python failed to run correctly',
        ANSWER="Please check the py log file in '@ScenarioDir@\_Log' for error messages."

    GOTO :ONERROR

    ABORT

endif  ;ReturnCode<>0


;DOS command to delete '__pycache__' folder
;  note: '/s' removes folder & contents of folder includling any subfolders
;  note: '/q' denotes quite mode, meaning doesn't ask for confirmation to delete
*(rmdir /s /q "__pycache__")



RUN PGM=NETWORK  MSG='select and calculate fields for TDM summary with factors'
    FILEI NETI[1]  = "@ScenarioDir@\7_PostProcessing\5_TDM2MOVES_Prep\gpdresultsforTDM2MOVES.dbf"
    SFF=FF_SPD
    AWDT_DY=DY_VOL
    AADT_DY=DY_VOL/FACAWDT
    dist=Distance;+DISTEXCEPT
    VMT_AWDT=DY_VOL*dist
    VMT_Jan=VMT_AWDT*FAC_JAN
    VMT_Jul=VMT_AWDT*FAC_JUL
    VMT_AADT=AADT_DY*dist
    FACJAN=FAC_JAN
    FACJUL=FAC_JUL
    AWDTFAC=FACAWDT
    AM_VMT_w=Distance*AM_VOL*FAC_JAN*FACAWDT
    MD_VMT_w=Distance*MD_VOL*FAC_JAN*FACAWDT
    PM_VMT_w=Distance*PM_VOL*FAC_JAN*FACAWDT
    EV_VMT_w=Distance*EV_VOL*FAC_JAN*FACAWDT
    AM_VMT_S=Distance*AM_VOL*FAC_JUL*FACAWDT
    MD_VMT_S=Distance*MD_VOL*FAC_JUL*FACAWDT
    PM_VMT_S=Distance*PM_VOL*FAC_JUL*FACAWDT
    EV_VMT_S=Distance*EV_VOL*FAC_JUL*FACAWDT

    FILEO LINKO="@ScenarioDir@\7_PostProcessing\5_TDM2MOVES_Prep\@runId@TDM_SummarywithFactors.dbf", INCLUDE= A,B,FT,SFF,CO_FIPS,city_fips,AWDT_DY,AADT_DY,VMT_Jan,VMT_Jul,VMT_AWDT,VMT_AADT,FACJAN,FACJUL,AWDTFAC,dist,AM_VOL,MD_VOL,PM_VOL,EV_VOL,AM_SPD,MD_SPD,PM_SPD,EV_SPD,AM_VMT_w,MD_VMT_w,PM_VMT_w,EV_VMT_w,AM_VMT_S,MD_VMT_S,PM_VMT_S,EV_VMT_S,lanes,am_vc,md_vc,pm_vc,ev_vc

ENDRUN

;==============================================================================
;                               Hail Mary Run Script
;==============================================================================

:BEGINMODEL
    ModelStep = 'BEGIN MODEL'
    
    ;get timestamp
    ModelStartTime = currenttime()
    
    ;initialize by reading in scenario general and specific parameters
    READ FILE = '0GeneralParameters.block'
    READ FILE = '1ControlCenter.block'
    
    ;set on error goto parameter (set label to jump to if an error occurs)
    ONRUNERRORGOTO='ONERROR'
    
    ;delete old prn files
    *(DEL *.PRN)

/*


:STEP0
    ModelStep = 'STEP 0 - Pre-Processing'
    
    ;get timestamp
    BegTime_IP = currenttime()
    
    ;folder setup and initial processing
    READ FILE = '..\..\..\2_ModelScripts\0_InputProcessing\a_Setup\0_FolderSetup.s'
    READ FILE = '..\..\..\2_ModelScripts\0_InputProcessing\a_Setup\1_InputSetup.s'

    if (Run_vizTool=1)
        READ FILE = '..\..\..\2_ModelScripts\0_InputProcessing\a_Setup\2_vizToolSetup.s'
    endif
    
    ;SE processing
    READ FILE = '..\..\..\2_ModelScripts\0_InputProcessing\b_SEProcessing\1_DemographicsAnalysis.s'
    READ FILE = '..\..\..\2_ModelScripts\0_InputProcessing\b_SEProcessing\2_UrbanizationTermTime.s'
    
    ;highway and transit network processing
    READ FILE = '..\..\..\2_ModelScripts\0_InputProcessing\c_NetworkProcessing\1_NetProcessor.s'
    READ FILE = '..\..\..\2_ModelScripts\0_InputProcessing\c_NetworkProcessing\2_FFSkim.s'
    READ FILE = '..\..\..\2_ModelScripts\0_InputProcessing\c_NetworkProcessing\3_TurnPenalty.s'
    READ FILE = '..\..\..\2_ModelScripts\0_InputProcessing\c_NetworkProcessing\4_Create_walk_xfer_access_links.s'
    READ FILE = '..\..\..\2_ModelScripts\0_InputProcessing\c_NetworkProcessing\5_WalkTransitSkim_Emp30MinTransit.s'
    
    ;exogenous trip table processing
    READ FILE = '..\..\..\2_ModelScripts\0_InputProcessing\d_TripTable\1_TripTable.s'
    READ FILE = '..\..\..\2_ModelScripts\0_InputProcessing\d_TripTable\2_External_TripTable.s'
    
    ;calculate time of day factors
    READ FILE = '..\..\..\2_ModelScripts\0_InputProcessing\e_TimeOfDayFactors\1_CalculateTimeOfDayFac.s'
    
    ;report model step run time
    READ FILE = '..\..\..\2_ModelScripts\0_InputProcessing\a_Setup\_TimeStamp_IP.block'



:STEP1
    ModelStep = 'STEP 1 - HH Disaggregation and Auto-Ownership'
    
    ;get timestamp
    BegTime_AO = currenttime()
    
    ;model scripts
    READ FILE = '..\..\..\2_ModelScripts\1_HHDisag_AutoOwn\1_LifeCycle.s'
    READ FILE = '..\..\..\2_ModelScripts\1_HHDisag_AutoOwn\2_HHDisaggregation.s'
    READ FILE = '..\..\..\2_ModelScripts\1_HHDisag_AutoOwn\3_AutoOwnership.s'
    
    ;report model step run time
    READ FILE = '..\..\..\2_ModelScripts\1_HHDisag_AutoOwn\_TimeStamp_AO.block'



:STEP2
    ModelStep = 'STEP 2 - Trip Generation'
    
    ;get timestamp
    BegTime_TG = currenttime()
    
    ;model scripts
    READ FILE = '..\..\..\2_ModelScripts\2_Tripgen\1_TripGen.s'
    
    ;report model step run time
    READ FILE = '..\..\..\2_ModelScripts\2_Tripgen\_TimeStamp_TG.block'



:STEP3
    ModelStep = 'STEP 3 - Trip Distribution'
    
    ;get timestamp
    BegTime_DS = currenttime()
    
    ;model scripts
    READ FILE = '..\..\..\2_ModelScripts\3_Distribute\1_Distribution.s'  
    READ FILE = '..\..\..\2_ModelScripts\3_Distribute\2_estimateHOTspeedtoll.s'
    
    if (Get_data_for_REMM<>1)
        READ FILE = '..\..\..\2_ModelScripts\3_Distribute\3_SumToDistricts_GRAVITY.s'
        READ FILE = '..\..\..\2_ModelScripts\3_Distribute\4_TLF_Distrib_PA.s'
        READ FILE = '..\..\..\2_ModelScripts\3_Distribute\5_SegmentSummary_Dist.s'
    endif
    
    ;report model step run time
    READ FILE = '..\..\..\2_ModelScripts\3_Distribute\_TimeStamp_DS.block'


*/
:STEP4
    ModelStep = 'STEP 4 - Mode Choice'
    
    ;get timestamp
    BegTime_MC = currenttime()
    
    ;model scripts
;    READ FILE = '..\..\..\2_ModelScripts\4_ModeChoice\01_Segmnt_TripsByDetailed.s'
;    READ FILE = '..\..\..\2_ModelScripts\4_ModeChoice\02_Segmnt_TransitAccessMarkets.s'
;    READ FILE = '..\..\..\2_ModelScripts\4_ModeChoice\03_Skim_auto.s'   
;    READ FILE = '..\..\..\2_ModelScripts\4_ModeChoice\04_Create_drive_access_links.s'
;    READ FILE = '..\..\..\2_ModelScripts\4_ModeChoice\05_Skim_Tran.s'
;    READ FILE = '..\..\..\2_ModelScripts\4_ModeChoice\06_HBW_logsums.s'
;    READ FILE = '..\..\..\2_ModelScripts\4_ModeChoice\07_HBW_dest_choice.s'
    READ FILE = '..\..\..\..\run_sets\bring-work-trips-closer-to-home\scripts\test.s'
    READ FILE = '..\..\..\2_ModelScripts\4_ModeChoice\08_TripTablesByPeriod.s'
    READ FILE = '..\..\..\2_ModelScripts\4_ModeChoice\09_Segmnt_PA_HBbyMC.s'
    READ FILE = '..\..\..\2_ModelScripts\4_ModeChoice\10_ConvertSomeXI2HBW.s'
    READ FILE = '..\..\..\2_ModelScripts\4_ModeChoice\11_MC_HBW_HBO_NHB_HBC.s '
    READ FILE = '..\..\..\2_ModelScripts\4_ModeChoice\12_EstimateHBSchModeShare.s'
    READ FILE = '..\..\..\2_ModelScripts\4_ModeChoice\13_vizTool_TripsByMode.s '
    
    if (Get_data_for_REMM<>1)
        READ FILE = '..\..\..\2_ModelScripts\4_ModeChoice\14_AsnTran.s'
        READ FILE = '..\..\..\2_ModelScripts\4_ModeChoice\16_SharesReport.s'
        READ FILE = '..\..\..\2_ModelScripts\4_ModeChoice\17_BoardingsReport.s'
        READ FILE = '..\..\..\2_ModelScripts\4_ModeChoice\18_SumToDistricts_FinalTripTables.s'
    endif
    
    ;report model step run time
    READ FILE = '..\..\..\2_ModelScripts\4_ModeChoice\_TimeStamp_MC.block'



:STEP5
    ModelStep = 'STEP 5 - Final Assignment'
    
    if (Get_data_for_REMM<>1)
        ;get timestamp
        BegTime_AS = currenttime()
        
        ;model scripts
        READ FILE = '..\..\..\2_ModelScripts\5_AssignHwy\01_Convert_PA_to_OD.s'
        READ FILE = '..\..\..\2_ModelScripts\5_AssignHwy\02_Assign_AM_MD_PM_EV.s'
        READ FILE = '..\..\..\2_ModelScripts\5_AssignHwy\04_SummarizeLoadedNetworks.s'
        READ FILE = '..\..\..\2_ModelScripts\5_AssignHwy\05_RemoveManagedLanes.s'
        READ FILE = '..\..\..\2_ModelScripts\5_AssignHwy\06_SegmentSummary.s'
        READ FILE = '..\..\..\2_ModelScripts\5_AssignHwy\07_PerformFinalNetSkim.s'
        READ FILE = '..\..\..\2_ModelScripts\5_AssignHwy\08_Access_to_Opportunity.s'
        READ FILE = '..\..\..\2_ModelScripts\5_AssignHwy\09_TAZ_Based_Metrics.s'
        
        ;report model step run time
        READ FILE = '..\..\..\2_ModelScripts\5_AssignHwy\_TimeStamp_AS.block'
    endif



:STEP6
    ModelStep = 'STEP 6 - REMM Input Preparation'
    
    if (Get_data_for_REMM=1)
        ;get timestamp
        BegTime_RM = currenttime()
        
        ;model scripts
        READ FILE = '..\..\..\2_ModelScripts\6_REMM\1_output_Logsum.s'
        READ FILE = '..\..\..\2_ModelScripts\6_REMM\2_output_Time_Auto_Trans_pk.s'
        READ FILE = '..\..\..\2_ModelScripts\6_REMM\3_output_LinkVolumeTAZlevel.s'
        READ FILE = '..\..\..\2_ModelScripts\6_REMM\4_output_Rail_Bus_Stops.s'
        READ FILE = '..\..\..\2_ModelScripts\6_REMM\5_avgTravelTime_byTAZ.s'
        READ FILE = '..\..\..\2_ModelScripts\6_REMM\6_Run_Parcel_Vol_Python_Script.s'
        
        ;report model step run time
        READ FILE = '..\..\..\2_ModelScripts\6_REMM\_TimeStamp_RM.block'
    endif



:STEP7
    ModelStep = 'STEP 7 - Post Processing'
    
    ;get timestamp
    BegTime_PP = currenttime()
    
    ;model scripts
    READ FILE = '..\..\..\2_ModelScripts\7_PostProcessing\0_DeleteTempFiles.s'
    
    ;model scripts
    if (Get_data_for_REMM<>1)
        
        ;model scripts
       ;READ FILE = '..\..\..\2_ModelScripts\7_PostProcessing\1_VMTproducedByTAZ.s'  
        
    endif
    
    ;report model step run time
    READ FILE = '..\..\..\2_ModelScripts\7_PostProcessing\_TimeStamp_PP.block'




:ENDMODEL
    ;close Cube Cluster widows (if using more than 100 cores, update index below)
    if (UseCubeCluster=1)
        *(Cluster.EXE  ClusterNodeID 2-100 CLOSE EXIT)
    endif
    
    
    if (SendEmailModelFinish=1)
        SENDMAIL,
            SMTPSERVER = 'smtp-relay.gmail.com',  
            FROM       = 'WFTDM@wfrc.org',
            TO         = 'username1@userdomain.org',
           ;CC         = 'username2@userdomain.org, username3@userdomain.org, username4@userdomain.org',
            SUBJECT    = 'Model Finished',
            MESSAGE    = 'The selected model steps appear to have run successfully for model run: ', 
                         Description, RID, ParentDir, ScenarioDir, UserName, UserCompany, ModelVersion
    endif
    
    
    ;report model step run time
    READ FILE = '..\..\..\2_ModelScripts\_TimeStamp_ModelSuccess.block'
    
    
    ;open vizTool in local host
    if (Run_vizTool=1)
        READ FILE = '..\..\..\2_ModelScripts\7_PostProcessing\2_OpenVizTool.s'
    endif
    
    
    ;quit model run
    Exit
    



;if an error occurs the process jumps to this location
:ONERROR
    ;close Cube Cluster widows (if using more than 100 cores, update index below)
    if (UseCubeCluster=1)
        *(Cluster.EXE  ClusterNodeID 2-100 CLOSE EXIT)
    endif
    
    
    ;model crahsed email;email sent if model crashed
    if (SendEmailModelCrash=1)
        SENDMAIL,
            SMTPSERVER = 'smtp-relay.gmail.com',  
            FROM       = 'WFTDM@wfrc.org',
            TO         = 'username1@userdomain.org',
           ;CC         = 'username2@userdomain.org, username3@userdomain.org, username4@userdomain.org',
            Subject    = 'Model Crashed',
            Message    = 'The following scenario crashed in: ', ModelStep,
                         Description, RID, ParentDir, ScenarioDir, UserName, UserCompany, ModelVersion
    endif
    
    
    ;report model step run time
    READ FILE = '..\..\..\2_ModelScripts\_TimeStamp_ModelCrashed.block'

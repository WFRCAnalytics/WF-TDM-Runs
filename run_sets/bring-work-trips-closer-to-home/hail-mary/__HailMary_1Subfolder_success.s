;==============================================================================
;                               Hail Mary Run Script
;==============================================================================

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
/*
:STEP0
    ModelStep = 'STEP 0 - Pre-Processing'
    BegTime_IP = currenttime() ;get timestamp
    
    READ FILE = '..\..\..\2_ModelScripts\0_InputProcessing\a_Setup\0_FolderSetup.s'
    READ FILE = '..\..\..\2_ModelScripts\0_InputProcessing\a_Setup\1_InputSetup.s'
    if (Run_vizTool=1)
        READ FILE = '..\..\..\2_ModelScripts\0_InputProcessing\a_Setup\2_vizToolSetup.s'
    endif
    READ FILE = '..\..\..\2_ModelScripts\0_InputProcessing\a_Setup\3_CheckGeneralParameters.s'
    READ FILE = '..\..\..\2_ModelScripts\0_InputProcessing\b_SEProcessing\1_DemographicsAnalysis.s'
    READ FILE = '..\..\..\2_ModelScripts\0_InputProcessing\b_SEProcessing\2_UrbanizationTermTime.s'
    READ FILE = '..\..\..\2_ModelScripts\0_InputProcessing\c_NetworkProcessing\1_NetProcessor.s'
    READ FILE = '..\..\..\2_ModelScripts\0_InputProcessing\c_NetworkProcessing\2_FFSkim.s'
    READ FILE = '..\..\..\2_ModelScripts\0_InputProcessing\c_NetworkProcessing\3_TurnPenalty.s'
    READ FILE = '..\..\..\2_ModelScripts\0_InputProcessing\c_NetworkProcessing\4_Create_walk_xfer_access_links.s'
    READ FILE = '..\..\..\2_ModelScripts\0_InputProcessing\c_NetworkProcessing\5_WalkTransitSkim_Emp30MinTransit.s'
    READ FILE = '..\..\..\2_ModelScripts\0_InputProcessing\d_TripTable\1_SpecialTripTable.s
    READ FILE = '..\..\..\2_ModelScripts\0_InputProcessing\d_TripTable\2_ExternalTripTable.s'
    READ FILE = '..\..\..\2_ModelScripts\0_InputProcessing\e_TimeOfDayFactors\1_CalculateTimeOfDayFac.s'
    if (Run_vizTool=1)
        READ FILE = '..\..\..\2_ModelScripts\0_InputProcessing\d_TripTable\1_SpecialTripTable_vizTool.s'
    endif
    READ FILE = '..\..\..\2_ModelScripts\0_InputProcessing\a_Setup\_TimeStamp_IP.block' ;report model step run time
    
:STEP1
    ModelStep = 'STEP 1 - HH Disaggregation and Auto-Ownership'
    BegTime_AO = currenttime() ;get timestamp
    
    READ FILE = '..\..\..\2_ModelScripts\1_HHDisag_AutoOwn\1_LifeCycle.s'
    READ FILE = '..\..\..\2_ModelScripts\1_HHDisag_AutoOwn\2_HHDisaggregation.s'
    READ FILE = '..\..\..\2_ModelScripts\1_HHDisag_AutoOwn\3_AutoOwnership.s'
    if (Run_vizTool=1)
        READ FILE = '..\..\..\2_ModelScripts\1_HHDisag_AutoOwn\3_AutoOwnership_vizTool.s'
    endif
    READ FILE = '..\..\..\2_ModelScripts\1_HHDisag_AutoOwn\_TimeStamp_AO.block' ;report model step run time
    
:STEP2
    ModelStep = 'STEP 2 - Trip Generation'
    BegTime_TG = currenttime() ;get timestamp
    
    READ FILE = '..\..\..\2_ModelScripts\2_Tripgen\1_TripGen.s'
    if (Run_vizTool=1)
        READ FILE = '..\..\..\2_ModelScripts\2_Tripgen\1_TripGen_vizTool.s'
    endif
    READ FILE = '..\..\..\2_ModelScripts\2_Tripgen\_TimeStamp_TG.block' ;report model step run time
    
:STEP3
    ModelStep = 'STEP 3 - Trip Distribution'
    BegTime_DS = currenttime() ;get timestamp
    
    READ FILE = '..\..\..\2_ModelScripts\3_Distribute\1_Distribution.s'  
    READ FILE = '..\..\..\2_ModelScripts\3_Distribute\2_estimateHOTspeedtoll.s'
    if (Get_data_for_REMM<>1)
        READ FILE = '..\..\..\2_ModelScripts\3_Distribute\3_SumToDistricts_GRAVITY.s'
        READ FILE = '..\..\..\2_ModelScripts\3_Distribute\4_TLF_Distrib_PA.s'
        READ FILE = '..\..\..\2_ModelScripts\3_Distribute\5_SegmentSummary_Dist.s'
    endif
    
    READ FILE = '..\..\..\2_ModelScripts\3_Distribute\_TimeStamp_DS.block' ;report model step run time

:STEP4
    ModelStep = 'STEP 4 - Mode Choice'
    BegTime_MC = currenttime() ;get timestamp
    
    READ FILE = '..\..\..\2_ModelScripts\4_ModeChoice\01_Segmnt_TripsByDetailed.s'
    READ FILE = '..\..\..\2_ModelScripts\4_ModeChoice\02_Segmnt_TransitAccessMarkets.s'
    READ FILE = '..\..\..\2_ModelScripts\4_ModeChoice\03_Skim_auto.s'
    READ FILE = '..\..\..\2_ModelScripts\4_ModeChoice\04_Create_drive_access_links.s'
    READ FILE = '..\..\..\2_ModelScripts\4_ModeChoice\05_Skim_Tran.s'
    READ FILE = '..\..\..\2_ModelScripts\4_ModeChoice\06_HBW_logsums.s'
    READ FILE = '..\..\..\2_ModelScripts\4_ModeChoice\07_HBW_dest_choice.s'
    READ FILE = '..\..\..\..\run_sets\bring-work-trips-closer-to-home\scripts\redistribute_hbw_trips.s'
    READ FILE = '..\..\..\2_ModelScripts\4_ModeChoice\08_TripTablesByPeriod.s'
    READ FILE = '..\..\..\2_ModelScripts\4_ModeChoice\09_Segmnt_PA_HBbyMC.s'
    READ FILE = '..\..\..\2_ModelScripts\4_ModeChoice\10_ConvertSomeXI2HBW.s'
    READ FILE = '..\..\..\2_ModelScripts\4_ModeChoice\11_MC_HBW_HBO_NHB_HBC.s'
    READ FILE = '..\..\..\2_ModelScripts\4_ModeChoice\12_EstimateHBSchModeShare.s'
    READ FILE = '..\..\..\2_ModelScripts\4_ModeChoice\13_EstimateIMZModeShare.s'
    READ FILE = '..\..\..\2_ModelScripts\4_ModeChoice\14_TripsByMode.s'
    if (Run_vizTool=1)
        READ FILE = '..\..\..\2_ModelScripts\4_ModeChoice\14_TripsByMode_vizTool.s'
    endif
    if (Get_data_for_REMM<>1)
        READ FILE = '..\..\..\2_ModelScripts\4_ModeChoice\15_AsnTran.s'
        READ FILE = '..\..\..\2_ModelScripts\4_ModeChoice\16_SharesReport.s'
        READ FILE = '..\..\..\2_ModelScripts\4_ModeChoice\17_BoardingsReport.s'
        READ FILE = '..\..\..\2_ModelScripts\4_ModeChoice\18_SumToDistricts_FinalTripTables.s'
        if (Run_vizTool=1)
            READ FILE = '..\..\..\2_ModelScripts\4_ModeChoice\16_SharesReport_vizTool.s'
            READ FILE = '..\..\..\2_ModelScripts\4_ModeChoice\17_BoardingsReport_vizTool.s'
            READ FILE = '..\..\..\2_ModelScripts\4_ModeChoice\18_SumToDistricts_FinalTripTables_vizTool.s'
        endif
    endif
    READ FILE = '..\..\..\2_ModelScripts\4_ModeChoice\_TimeStamp_MC.block' ;report model step run time

:STEP5
    ModelStep = 'STEP 5 - Final Assignment'
    BegTime_AS = currenttime() ;get timestamp

    if (Get_data_for_REMM<>1)
        READ FILE = '..\..\..\2_ModelScripts\5_AssignHwy\01_Convert_PA_to_OD.s'
        READ FILE = '..\..\..\2_ModelScripts\5_AssignHwy\02_Assign_AM_MD_PM_EV.s'
        READ FILE = '..\..\..\2_ModelScripts\5_AssignHwy\04_SummarizeLoadedNetworks.s'
        READ FILE = '..\..\..\2_ModelScripts\5_AssignHwy\05_RemoveManagedLanes.s'
        READ FILE = '..\..\..\2_ModelScripts\5_AssignHwy\06_SegmentSummary.s'
        READ FILE = '..\..\..\2_ModelScripts\5_AssignHwy\07_PerformFinalNetSkim.s'
        READ FILE = '..\..\..\2_ModelScripts\5_AssignHwy\08_Access_to_Opportunity.s'
        READ FILE = '..\..\..\2_ModelScripts\5_AssignHwy\09_TAZ_Based_Metrics.s'
        if (Run_vizTool=1)
            READ FILE = '..\..\..\2_ModelScripts\5_AssignHwy\06_SegmentSummary_vizTool.s'
            READ FILE = '..\..\..\2_ModelScripts\5_AssignHwy\08_Access_to_Opportunity_vizTool.s'
            READ FILE = '..\..\..\2_ModelScripts\5_AssignHwy\09_TAZ_Based_Metrics_vizTool.s'
        endif
    endif
    READ FILE = '..\..\..\2_ModelScripts\5_AssignHwy\_TimeStamp_AS.block' ;report model step run time
    
:STEP6
    ModelStep = 'STEP 6 - REMM Input Preparation'
    BegTime_RM = currenttime() ;get timestamp
    
    if (Get_data_for_REMM=1)
        READ FILE = '..\..\..\2_ModelScripts\6_REMM\1_output_Logsum.s'
        READ FILE = '..\..\..\2_ModelScripts\6_REMM\2_output_Time_Auto_Trans_pk.s'
        READ FILE = '..\..\..\2_ModelScripts\6_REMM\3_output_LinkVolumeTAZlevel.s'
        READ FILE = '..\..\..\2_ModelScripts\6_REMM\4_output_Rail_Bus_Stops.s'
        READ FILE = '..\..\..\2_ModelScripts\6_REMM\5_avgTravelTime_byTAZ.s'
        READ FILE = '..\..\..\2_ModelScripts\6_REMM\6_Run_Parcel_Vol_Python_Script.s'
    endif
    READ FILE = '..\..\..\2_ModelScripts\6_REMM\_TimeStamp_RM.block' ;report model step run time

:STEP7
    ModelStep = 'STEP 7 - Post Processing'
    BegTime_PP = currenttime() ;get timestamp
    
    READ FILE = '..\..\..\2_ModelScripts\7_PostProcessing\0_DeleteTempFiles.s'
    if (Get_data_for_REMM<>1)
        ;READ FILE = '..\..\..\2_ModelScripts\7_PostProcessing\1_VMTproducedByTAZ.s'  
    endif
    READ FILE = '..\..\..\2_ModelScripts\7_PostProcessing\_TimeStamp_PP.block' ;report model step run time
*/
:ENDMODEL
    ;close Cube Cluster widows (if using more than 100 cores, update index below)
    if (UseCubeCluster=1)
        *(Cluster.EXE  ClusterNodeID 2-100 CLOSE EXIT)
    endif
;    READ FILE = '..\..\..\2_ModelScripts\_TimeStamp_ModelSuccess.block' ;report model step run time
;    if (Run_vizTool=1)
;        READ FILE = '..\..\..\2_ModelScripts\7_PostProcessing\2_OpenVizTool.s'
;    endif
    Exit ;quit model run
    
;if an error occurs the process jumps to this location
:ONERROR
    ;close Cube Cluster widows (if using more than 100 cores, update index below)
    if (UseCubeCluster=1)
        *(Cluster.EXE  ClusterNodeID 2-100 CLOSE EXIT)
    endif
    READ FILE = '..\..\..\2_ModelScripts\_TimeStamp_ModelCrashed.block' ;report model step run time

;=============================================================================================================
; __HailMary_1Subfolder_ato_detail.s
;
; Minimal custom driver script for the `city-detail` scenario in this run
; set. Deliberately runs NONE of the model pipeline (no input processing, no
; disaggregation, no trip gen/distribution/mode choice/assignment) -- this
; scenario's raw folder is seeded via start_from_copy from `base` (an
; already-converged run), so everything upstream already exists on disk.
; This driver reads the two files the copied model pipeline itself always
; reads first (Control Center, then GeneralParameters.block -- same as the
; TDM's own default driver script, e.g.
; tdm/Scenarios/_default/__HailMary_1Subfolder.s), then runs only the one
; new step: access_to_opportunity_detail.s.
;
; See reports/run_sets/accessible-jobs-ato/scoping.qmd and
; run_sets/accessible-jobs-ato/scripts/access_to_opportunity_detail.s for
; what that step actually computes.
;=============================================================================================================

    READ FILE = '_ControlCenter.block'
    READ FILE = '..\..\..\1_Inputs\0_GlobalData\GeneralParameters.block'

    READ FILE = '..\..\..\..\run_sets\accessible-jobs-ato\scripts\access_to_opportunity_detail.s'

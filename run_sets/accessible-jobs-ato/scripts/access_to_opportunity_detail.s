;=============================================================================================================
; access_to_opportunity_detail.s
;
; Sibling to tdm/2_ModelScripts/5_AssignHwy/08_Access_to_Opportunity.s -- NOT an
; edit to that script. 08's output is a real input to WFRC's REMM land-use
; model (via its DEVACRES>0 filter) and must stay untouched. This script
; answers a different question: not "what is TAZ i's own decayed access
; score," but "which cities is that score actually coming from" -- so it can
; be rolled up to Internal/Outbound/Inbound by city
; (see reports/run_sets/accessible-jobs-ato/scoping.qmd).
;
; Differences from 08_Access_to_Opportunity.s, all deliberate simplifications
; for this first version (see scoping.qmd's "Decisions still needed" table):
;   - Accumulates into City x City arrays (keyed by a TAZID -> CityIdx
;     crosswalk, run_sets/accessible-jobs-ato/inputs/city_index.csv, built by
;     scripts/build_city_index.py from WFv1000_TAZ.dbf's CITY_UGRC field)
;     instead of a per-origin-TAZ scalar -- the entire point of this script.
;     This crosswalk is a per-TAZ file, not the minimal ~82-row one this
;     script first tried -- see the FILEI DBI[2] comment below for why.
;   - No DEVACRES filter -- every real TAZ contributes, developable or not.
;   - Transit walk-access and drive-access are kept as SEPARATE output
;     columns, not collapsed to MAX(walk, drive) per TAZ pair before rolling
;     up -- collapsing first would change the meaning of a city-level sum in
;     a way that's hard to justify. The app can take the max downstream if
;     it wants a single "best transit" number.
;   - CORRECTED (2026-09-08): an earlier version of this script dropped
;     08_Access_to_Opportunity.s's "actual/realized" (act_*) weighting
;     entirely, reasoning it wasn't needed for a city rollup of the raw
;     measure. That was wrong -- without it, summing every TAZ i in a city
;     produces numbers that scale with how many TAZs the city has, not a
;     meaningful accessibility figure (a big city's total inflates just from
;     having more TAZs, independent of how good its access actually is).
;     This version restores the weighting: each (i,j) contribution to
;     Job_<mode>/Retail_<mode>/Industrial_<mode>/Other_<mode> is multiplied
;     by HH_i (the number of households AT origin i -- "how many people this
;     origin's access actually serves"); each contribution to HH_<mode> is
;     multiplied by Job_i (the number of jobs AT i, since HH_<mode> measures
;     labor supply accessible TO a job at i). A second small output file
;     (CityTotals, one row per city) carries each home_city's total HH and
;     total Job, so the app can DIVIDE the weighted sum by the matching
;     total and get a proper household-weighted (or job-weighted) AVERAGE --
;     not a total that mechanically grows with city size. See
;     process_data.py in APP-ATO-Interactive for where that division happens.
;   - ADDED (2026-09-07): "average opportunity time" -- for the app's Access
;     Summary, a plain-language companion to the ATO score itself: not just
;     "how much access," but "at what average travel time is that access
;     actually being realized." For each (i,j) pair the same per-mode
;     travel time already computed for the ATO_Weight lookup (mw[110] auto,
;     mw[200] transit walk-access, mw[250] transit drive-access, mw[140]
;     bike, mw[150] walk) is accumulated into a second set of City x City
;     arrays, weighted exactly the same way as the Job_*/HH_* columns
;     themselves (W_<mode> * Job_j * HH_i for the Jobs side, W_<mode> * HH_j
;     * Job_i for the Households side) -- so dividing this new sum by the
;     matching already-existing Job_<mode>/HH_<mode> sum (in process_data.py,
;     not here) gives a proper access-weighted AVERAGE travel time, not a
;     naive mean across TAZ pairs that would be dominated by far-away,
;     barely-accessible ones. Sector breakdown (Retail/Industrial/Other)
;     does not get its own time column -- not asked for, and would just
;     repeat the Job_<mode> travel time weighted a different way for a
;     number nobody's asked to see yet.
;   - ADDED (2026-09-07): auto congestion/circuity Loss_* decomposition,
;     restored from 08_Access_to_Opportunity.s's own methodology (previously
;     dropped for v1, see above -- this run now adds it back at the city
;     level). 08 computes THREE auto access variants per TAZ, differing only
;     in which travel time feeds the same ATO_Weight(1, ...) decay curve:
;     congested (Skm_AM/PM, already used for the Job_Auto/HH_Auto columns
;     above), free-flow (Skm_FF.mtx, new FILEI MATI[15] above), and
;     straight-line (TAZ centroid distance / a running-average free-flow
;     speed, using the same Node_X/Node_Y and mw[133] straight-line distance
;     already computed for bike/walk). Comparing them isolates two distinct
;     causes of access loss:
;       Loss_Job_Cong = JobAutoFF - Job_Auto      (congestion's own cost --
;         the gap between what's reachable at free-flow speed vs actually
;         reachable once congestion is added)
;       Loss_Job_Net  = JobAutoSL - JobAutoFF     (network circuity's cost --
;         the gap between an idealized straight-line trip and the real free-
;         flow network path, i.e. how much the actual road network's
;         indirectness costs relative to "as the crow flies")
;     (and the HH_* mirror of each, using the Job_i weighting HH_<mode>
;     already uses). Both differences are computed in process_data.py, not
;     here -- this script only accumulates the three City x City sums
;     (CityJobAutoFF/CityJobAutoSL/CityHHAutoFF/CityHHAutoSL, weighted
;     identically to CityJob_Auto/CityHH_Auto) needed to take them. Auto
;     only, matching 08's own scope -- 08 never built this decomposition for
;     transit/bike/walk either.
;     NOTE: the run immediately after this was first added showed
;     JobAutoFF/HHAutoFF collapsing to ~0 (or exactly 0) for nearly every
;     external city pair, which would have meant free-flow access was
;     LOWER than congested access -- backwards, since a shorter free-flow
;     time should always decay-weight to at least as much access. A
;     targeted diagnostic (temporary PRINT FILE= dump of mw[110]/mw[120]/
;     mw[130] and their ATO_Weight() results for a known-affected city pair,
;     since 2026-09-07 removed once confirmed) showed the per-(i,j)-pair
;     math was correct and monotonic (congested < free-flow < straight-line
;     weight, as expected) -- yet the VERY NEXT full run (identical
;     accumulation logic, no code change in between) produced a correct,
;     sensible JobAutoFF > Job_Auto for the same city pair. Never
;     reproduced after that. Whatever caused the one bad run was not this
;     script's own logic (confirmed by an unchanged-logic re-run fixing it)
;     -- if it recurs, re-add a diagnostic like the one described above
;     rather than assuming the formula itself is wrong again.
;   - ADDED (2026-09-08): sector-specific Loss_* decomposition. The auto
;     Loss_Cong/Loss_Net columns above were built against Job_Auto only
;     (all sectors combined) -- selecting a sector in the app changed which
;     jobs counted for the Job_<mode>/JobTimeWt_<mode> columns but left the
;     "Access Lost" panel showing the same all-sectors congestion/circuity
;     numbers regardless, a real gap found only after shipping (same
;     mistake, and same fix shape, as the average-opportunity-time sector
;     gap above). Adds CityRetailAutoFF/SL, CityIndustrialAutoFF/SL,
;     CityOtherAutoFF/SL -- same free-flow/straight-line weighting as
;     CityJobAutoFF/SL, just multiplying Retail_j/Industrial_j/Other_j
;     instead of Job_j. process_data.py takes the same differences
;     (Loss_Retail_Cong = RetailAutoFF - Retail_Auto, etc.) it already takes
;     for the all-sectors version.
;
; Run manually against an already-populated scenario folder (this run set's
; `base` scenario is registered via manual_scenario_folder, never through
; run-scenario) -- no new Cube Voyager full-model run needed. Reads the same
; already-computed skims and SE_File.dbf that scenario folder already has.
;=============================================================================================================

;print file to help identify error if model crashes
*(ECHO model crashed > access_to_opportunity_detail.txt)


RUN PGM=MATRIX MSG='Post Processing: Calculate Access to Opportunity (City x City detail)'
FILEI ZDATI[1] = '@ScenarioDir@\0_InputProcessing\SE_File.dbf'

FILEI DBI[1] = '@ScenarioDir@\0_InputProcessing\ScenarioNet\scenario - Node.dbf',
    AUTOARRAY=ALLFIELDS,
    SORT=N

; TAZID -> CityIdx crosswalk (run_sets/accessible-jobs-ato/inputs/city_index.csv,
; built by scripts/build_city_index.py from WFv1000_TAZ.dbf's CITY_UGRC field).
; Two earlier approaches were tried against real Cube Voyager and reverted,
; both confirmed via an actual run (TPPL1791.PRN, 2026-09-07), not guessed:
;   1. Reading WFv1000_TAZ.dbf's CITY_UGRC directly and translating it via a
;      LOOKUP with STRING=T -- Cube's LOOKUP command has no such option
;      ("F(018): STRING is invalid key").
;   2. Falling back to the numeric CITY_FIPS field already on that same
;      file -- fails too, for a data reason, not a syntax one: CITY_FIPS=0
;      is shared by Hill AFB and unincorporated county land in the real
;      TAZ data, a genuine collision.
; This file sidesteps both: TAZID is always unique, and it's loaded as a
; plain DBI with DELIMITER=',' -- the exact same mechanism this TDM's own
; production code already uses to read a CSV zone file (see
; tdm/2_ModelScripts/0_InputProcessing/b_SEProcessing/1_DemographicsAnalysis.s's
; WFRC_SEFile/MAG_SEFile FILEI DBI lines) -- then populated into a
; TAZID-indexed array via a LOOP, the same pattern already used below for
; Node_X/Node_Y from scenario Node.dbf. No LOOKUP() call at all this time.
; AUTOARRAY=ALLFIELDS and SORT=TAZID are both present in 1_DemographicsAnalysis.s's
; own WFRC_SEFile/MAG_SEFile DBI declarations even with explicit column
; mapping -- dropped here on a first attempt as apparently unnecessary,
; which was wrong: without AUTOARRAY=ALLFIELDS, dba.2.TAZID/dba.2.CityIdx
; don't exist at all ("F(161): dba.2.TAZID is unrecognized variable name",
; confirmed via TPPL1792.PRN, 2026-09-07). Matching the proven pattern
; exactly this time instead of guessing which parts are load-bearing.
FILEI DBI[2] = '..\..\..\..\run_sets\accessible-jobs-ato\inputs\city_index.csv',
    DELIMITER=',',
    TAZID   = #01,
    CityIdx =  02,
    AUTOARRAY=ALLFIELDS,
    SORT=TAZID

; Congested auto (AM forward / PM transpose, composite peak), plus the
; free-flow skim (for the congestion/circuity Loss_* decomposition -- see
; the 2026-09-07 header addition below). Straight-line auto doesn't need its
; own skim file -- it's derived from the same TAZ centroid nodes already
; loaded for bike/walk (Node_X/Node_Y) plus this free-flow skim's own
; distance field, same as 08_Access_to_Opportunity.s does.
FILEI MATI[01] = '@ScenarioDir@\5_AssignHwy\5_FinalNetSkims\Skm_AM.mtx'
FILEI MATI[02] = '@ScenarioDir@\5_AssignHwy\5_FinalNetSkims\Skm_PM.mtx'

FILEI MATI[03] = '@ScenarioDir@\4_ModeChoice\1a_Skims\skm_w4_Pk.mtx'
FILEI MATI[04] = '@ScenarioDir@\4_ModeChoice\1a_Skims\skm_w5_Pk.mtx'
FILEI MATI[05] = '@ScenarioDir@\4_ModeChoice\1a_Skims\skm_w6_Pk.mtx'
FILEI MATI[06] = '@ScenarioDir@\4_ModeChoice\1a_Skims\skm_w7_Pk.mtx'
FILEI MATI[07] = '@ScenarioDir@\4_ModeChoice\1a_Skims\skm_w8_Pk.mtx'
FILEI MATI[08] = '@ScenarioDir@\4_ModeChoice\1a_Skims\skm_w9_Pk.mtx'

FILEI MATI[09] = '@ScenarioDir@\4_ModeChoice\1a_Skims\skm_d4_Pk.mtx'
FILEI MATI[10] = '@ScenarioDir@\4_ModeChoice\1a_Skims\skm_d5_Pk.mtx'
FILEI MATI[11] = '@ScenarioDir@\4_ModeChoice\1a_Skims\skm_d6_Pk.mtx'
FILEI MATI[12] = '@ScenarioDir@\4_ModeChoice\1a_Skims\skm_d7_Pk.mtx'
FILEI MATI[13] = '@ScenarioDir@\4_ModeChoice\1a_Skims\skm_d8_Pk.mtx'
FILEI MATI[14] = '@ScenarioDir@\4_ModeChoice\1a_Skims\skm_d9_Pk.mtx'

; Free-flow auto skim -- same file 08_Access_to_Opportunity.s's own MATI[03]
; reads, added here only for the Loss_Cong/Loss_Net decomposition (see the
; 2026-09-07 header addition below).
FILEI MATI[15] = '@ScenarioDir@\5_AssignHwy\5_FinalNetSkims\Skm_FF.mtx'

FILEI LOOKUPI[1] = '@ModelDir@\1_Inputs\0_GlobalData\7_ATO\ATO_Weight.csv'

FILEO PRINTO[1] = '@ScenarioDir@\5_AssignHwy\4_Summaries\@runId@Access_to_Opportunity_CityDetail.csv'

; Second output: one row per city, its total HH and total Job -- the
; denominators the app divides the (now HH_i/Job_i-weighted) CityDetail
; table by to get a per-household/per-job AVERAGE instead of a raw sum that
; scales with how many TAZs the city has.
FILEO PRINTO[2] = '@ScenarioDir@\5_AssignHwy\4_Summaries\@runId@Access_to_Opportunity_CityTotals.csv'


    ;=========================================================================================================
    ;script parameters -----------------------------------------------------------------------------------
    ZONES   = @Usedzones@
    ZONEMSG = 10

    ; Must match build_city_index.py's NUM_CITIES output for the current
    ; run_sets/accessible-jobs-ato/inputs/city_index.csv -- re-run that
    ; script and update this constant (both here AND in the ARRAY
    ; declaration below) if WFv1000_TAZ.dbf's city assignments ever change.
    ; Confirmed via a real Cube Voyager run (TPPL1791.PRN, 2026-09-07):
    ; ARRAY dimensions must be a literal integer, not a variable -- using
    ; NUM_CITIES there fails with "ARRAY ...=NUM_CITIES is invalid value",
    ; cascading into "City_j has incorrect number of subscripts" everywhere
    ; the array is used. LOOP bounds, unlike ARRAY dimensions, do accept a
    ; variable (used below and in 08_Access_to_Opportunity.s itself), so
    ; NUM_CITIES is still used there.
    NUM_CITIES = 82

    ;decay weight lookup (same curve 08_Access_to_Opportunity.s uses)
    LOOKUP LOOKUPI=1,
        INTERPOLATE=T,
        NAME=ATO_Weight,
        LOOKUP[1]=1, RESULT=2,     ;auto
        LOOKUP[2]=1, RESULT=3,     ;w_transit
        LOOKUP[3]=1, RESULT=4,     ;d_transit
        LOOKUP[4]=1, RESULT=5,     ;bike
        LOOKUP[5]=1, RESULT=6      ;walk

    ;City x City accumulator arrays -- persist across the whole zone loop,
    ;zeroed once at i=1, never reset per-i (unlike 08's per-origin scalars).
    ;
    ;Flattened to ONE dimension (82*82=6724), not a genuine 2D array.
    ;Confirmed via three real Cube Voyager runs (TPPL1792/1793/1794.PRN,
    ;2026-09-07): every attempt to use these as ARRAY name = 82, 82 with a
    ;two-subscript [a,b] access failed with "incorrect number of
    ;subscripts" on EVERY usage, regardless of whether the subscript
    ;variables were pre-declared inside or outside a loop (both were tried).
    ;That comma-list syntax is what 08_Access_to_Opportunity.s's own
    ;confirmed-working ARRAY Node_X = N, Node_Y = N already uses to declare
    ;multiple separate ONE-dimensional arrays in one statement -- almost
    ;certainly it does the same thing here (silently declaring something
    ;other than a true 2D array), not a genuine multi-dimensional array
    ;feature. Rather than keep guessing at Cube's real 2D array syntax,
    ;flattening via CityFlat = (City_i-1)*82 + City_j and single-subscript
    ;access sidesteps the question entirely, using only the two array
    ;patterns already proven safe in this exact script (a plain one-
    ;dimensional ARRAY with a literal size, indexed by one integer).
    ARRAY CityJob_Auto      = 6724,
          CityJob_TranWalk  = 6724,
          CityJob_TranDrive = 6724,
          CityJob_Bike      = 6724,
          CityJob_Walk      = 6724,
          CityHH_Auto       = 6724,
          CityHH_TranWalk   = 6724,
          CityHH_TranDrive  = 6724,
          CityHH_Bike       = 6724,
          CityHH_Walk       = 6724

    ; "Average opportunity time" numerators -- travel time weighted exactly
    ; the same way as CityJob_*/CityHH_* above (see the file-header comment).
    ; Divide by the matching CityJob_<mode>/CityHH_<mode> value (already
    ; accumulated above) in process_data.py to get the access-weighted
    ; average travel time; not pre-divided here, same reasoning as
    ; CityTotals below (push division to Python, keep this script a dumb
    ; accumulator).
    ARRAY CityJobTimeWt_Auto      = 6724,
          CityJobTimeWt_TranWalk  = 6724,
          CityJobTimeWt_TranDrive = 6724,
          CityJobTimeWt_Bike      = 6724,
          CityJobTimeWt_Walk      = 6724,
          CityHHTimeWt_Auto       = 6724,
          CityHHTimeWt_TranWalk   = 6724,
          CityHHTimeWt_TranDrive  = 6724,
          CityHHTimeWt_Bike       = 6724,
          CityHHTimeWt_Walk       = 6724

    ; Free-flow and straight-line auto access sums -- same weighting as
    ; CityJob_Auto/CityHH_Auto above, but decayed by free-flow travel time
    ; (Skm_FF.mtx) or straight-line-derived travel time instead of congested
    ; travel time. process_data.py subtracts these from (or against each
    ; other and) CityJob_Auto/CityHH_Auto to get the congestion/circuity
    ; Loss_* decomposition -- see the file-header comment. Auto only,
    ; matching 08_Access_to_Opportunity.s's own scope for this decomposition.
    ARRAY CityJobAutoFF = 6724,
          CityJobAutoSL = 6724,
          CityHHAutoFF  = 6724,
          CityHHAutoSL  = 6724

    ; Per-sector free-flow/straight-line auto access sums -- same idea as
    ; CityJobAutoFF/SL above, so the app's Access Lost panel actually
    ; responds to the Sector toggle instead of always showing the
    ; all-sectors congestion/circuity numbers (see the 2026-09-08 header
    ; addition). Jobs-side only, same as CityRetail_*/CityIndustrial_*/
    ; CityOther_* below -- a household isn't sector-typed.
    ARRAY CityRetailAutoFF     = 6724,
          CityRetailAutoSL     = 6724,
          CityIndustrialAutoFF = 6724,
          CityIndustrialAutoSL = 6724,
          CityOtherAutoFF      = 6724,
          CityOtherAutoSL      = 6724

    ; Sector breakdown of Job_* (RETEMP/INDEMP/OTHEMP, already on SE_File.dbf,
    ; loaded above as ZDATI[1] -- these three sum to TOTEMP by construction,
    ; same source CLAUDE.md's "TDM's own sector categories" already
    ; describes). Jobs-side only -- a household isn't sector-typed, so this
    ; has no HH_* equivalent. Added after the app-side rewrite surfaced that
    ; this was recommended in scoping.qmd's decision table but never
    ; actually built into this script the first time around.
    ARRAY CityRetail_Auto      = 6724,
          CityRetail_TranWalk  = 6724,
          CityRetail_TranDrive = 6724,
          CityRetail_Bike      = 6724,
          CityRetail_Walk      = 6724,
          CityIndustrial_Auto      = 6724,
          CityIndustrial_TranWalk  = 6724,
          CityIndustrial_TranDrive = 6724,
          CityIndustrial_Bike      = 6724,
          CityIndustrial_Walk      = 6724,
          CityOther_Auto      = 6724,
          CityOther_TranWalk  = 6724,
          CityOther_TranDrive = 6724,
          CityOther_Bike      = 6724,
          CityOther_Walk      = 6724

    ; "Average opportunity time" numerators for the Sector filter -- same
    ; idea as CityJobTimeWt_*/CityHHTimeWt_* above, but per sector, so the
    ; app's avg-time stat actually changes when the Sector toggle (Retail/
    ; Industrial/Office-Other) is used instead of silently always reporting
    ; the all-sectors figure (a real gap found after shipping the all-
    ; sectors version -- see APP-ATO-Interactive's queryAvgTime()).
    ARRAY CityRetailTimeWt_Auto      = 6724,
          CityRetailTimeWt_TranWalk  = 6724,
          CityRetailTimeWt_TranDrive = 6724,
          CityRetailTimeWt_Bike      = 6724,
          CityRetailTimeWt_Walk      = 6724,
          CityIndustrialTimeWt_Auto      = 6724,
          CityIndustrialTimeWt_TranWalk  = 6724,
          CityIndustrialTimeWt_TranDrive = 6724,
          CityIndustrialTimeWt_Bike      = 6724,
          CityIndustrialTimeWt_Walk      = 6724,
          CityOtherTimeWt_Auto      = 6724,
          CityOtherTimeWt_TranWalk  = 6724,
          CityOtherTimeWt_TranDrive = 6724,
          CityOtherTimeWt_Bike      = 6724,
          CityOtherTimeWt_Walk      = 6724

    ARRAY Node_X = @UsedZones@,
          Node_Y = @UsedZones@,
          CityIdx_by_TAZ = @UsedZones@

    ; Per-city (not per-city-pair) totals -- the denominators for the
    ; HH_i/Job_i weighting above. Literal size 82 (NUM_CITIES), same
    ; one-dimensional pattern as everything else here.
    ARRAY CityHHTotal = 82,
          CityJobTotal = 82


    ;print status to console -------------------------------------------------------------------------------
    PrintProgress = INT(i / @UsedZones@ * 100)
    PrintProgInc = 1

    if (i=1)
        PRINT PRINTO=0, LIST='Processing: ', PrintProgress(5.0), '%'
        CheckProgress = PrintProgInc

        ;zero the accumulators explicitly (self-documenting; Cube zero-inits
        ;ARRAY on declaration, but this makes the "accumulate, never reset"
        ;contract obvious to a future reader). Single flat loop, 1..6724 --
        ;see the ARRAY comment above for why these are flattened.
        LOOP CityFlat = 1, 6724
            CityJob_Auto[CityFlat]      = 0
            CityJob_TranWalk[CityFlat]  = 0
            CityJob_TranDrive[CityFlat] = 0
            CityJob_Bike[CityFlat]      = 0
            CityJob_Walk[CityFlat]      = 0
            CityHH_Auto[CityFlat]       = 0
            CityHH_TranWalk[CityFlat]   = 0
            CityHH_TranDrive[CityFlat]  = 0
            CityHH_Bike[CityFlat]       = 0
            CityHH_Walk[CityFlat]       = 0
            CityJobTimeWt_Auto[CityFlat]      = 0
            CityJobTimeWt_TranWalk[CityFlat]  = 0
            CityJobTimeWt_TranDrive[CityFlat] = 0
            CityJobTimeWt_Bike[CityFlat]      = 0
            CityJobTimeWt_Walk[CityFlat]      = 0
            CityHHTimeWt_Auto[CityFlat]       = 0
            CityHHTimeWt_TranWalk[CityFlat]   = 0
            CityHHTimeWt_TranDrive[CityFlat]  = 0
            CityHHTimeWt_Bike[CityFlat]       = 0
            CityHHTimeWt_Walk[CityFlat]       = 0
            CityJobAutoFF[CityFlat] = 0
            CityJobAutoSL[CityFlat] = 0
            CityHHAutoFF[CityFlat]  = 0
            CityHHAutoSL[CityFlat]  = 0
            CityRetail_Auto[CityFlat]        = 0
            CityRetail_TranWalk[CityFlat]    = 0
            CityRetail_TranDrive[CityFlat]   = 0
            CityRetail_Bike[CityFlat]        = 0
            CityRetail_Walk[CityFlat]        = 0
            CityIndustrial_Auto[CityFlat]     = 0
            CityIndustrial_TranWalk[CityFlat] = 0
            CityIndustrial_TranDrive[CityFlat]= 0
            CityIndustrial_Bike[CityFlat]     = 0
            CityIndustrial_Walk[CityFlat]     = 0
            CityOther_Auto[CityFlat]         = 0
            CityOther_TranWalk[CityFlat]     = 0
            CityOther_TranDrive[CityFlat]    = 0
            CityOther_Bike[CityFlat]         = 0
            CityOther_Walk[CityFlat]         = 0
            CityRetailTimeWt_Auto[CityFlat]      = 0
            CityRetailTimeWt_TranWalk[CityFlat]  = 0
            CityRetailTimeWt_TranDrive[CityFlat] = 0
            CityRetailTimeWt_Bike[CityFlat]      = 0
            CityRetailTimeWt_Walk[CityFlat]      = 0
            CityIndustrialTimeWt_Auto[CityFlat]      = 0
            CityIndustrialTimeWt_TranWalk[CityFlat]  = 0
            CityIndustrialTimeWt_TranDrive[CityFlat] = 0
            CityIndustrialTimeWt_Bike[CityFlat]      = 0
            CityIndustrialTimeWt_Walk[CityFlat]      = 0
            CityOtherTimeWt_Auto[CityFlat]      = 0
            CityOtherTimeWt_TranWalk[CityFlat]  = 0
            CityOtherTimeWt_TranDrive[CityFlat] = 0
            CityOtherTimeWt_Bike[CityFlat]      = 0
            CityOtherTimeWt_Walk[CityFlat]      = 0
            CityRetailAutoFF[CityFlat]     = 0
            CityRetailAutoSL[CityFlat]     = 0
            CityIndustrialAutoFF[CityFlat] = 0
            CityIndustrialAutoSL[CityFlat] = 0
            CityOtherAutoFF[CityFlat]      = 0
            CityOtherAutoSL[CityFlat]      = 0
        ENDLOOP

        LOOP CityOnly = 1, NUM_CITIES
            CityHHTotal[CityOnly]  = 0
            CityJobTotal[CityOnly] = 0
        ENDLOOP

    elseif (PrintProgress=CheckProgress)
        PRINT PRINTO=0, LIST='Processing: ', PrintProgress(5.0), '%'
        CheckProgress = CheckProgress + PrintProgInc
    endif


    ;populate Node XY coord arrays once (needed for bike/walk straight-line distance)
    if (i=1)
        LOOP numrec=1, dbi.1.NUMRECORDS
            NodeNum = dba.1.N[numrec]
            if (NodeNum=1-@UsedZones@)  Node_X[NodeNum] = dba.1.X[numrec]
            if (NodeNum=1-@UsedZones@)  Node_Y[NodeNum] = dba.1.Y[numrec]
            if (NodeNum=@UsedZones@)  BREAK
        ENDLOOP
    endif


    ;populate CityIdx_by_TAZ once from city_index.csv -- same LOOP-over-records
    ;pattern as Node_X/Node_Y just above, not a LOOKUP() call (see the FILEI
    ;DBI[2] comment above for why). Only real TAZs (3,562 rows) are in the
    ;file -- dummy/external zone slots are left at 0, but those zone numbers
    ;are never read (both the outer i-loop and every JLOOP below exclude
    ;@dummyzones@/@externalzones@).
    if (i=1)
        LOOP numrec2=1, dbi.2.NUMRECORDS
            CityTAZ = dba.2.TAZID[numrec2]
            if (CityTAZ=1-@UsedZones@)  CityIdx_by_TAZ[CityTAZ] = dba.2.CityIdx[numrec2]
        ENDLOOP
    endif


    ;=========================================================================================================
    ;per-origin work (skip dummy & external zones, same exclusion 08 uses)
    if (!(i=@dummyzones@, @externalzones@))

        City_i = CityIdx_by_TAZ[i]
        HH_i   = zi.1.TOTHH[i]
        Job_i  = zi.1.TOTEMP[i]

        ; Accumulate this TAZ's own HH/Job total into its city's running
        ; total exactly once (i is fixed for this whole outer-loop pass) --
        ; these are the denominators the app divides the weighted sums
        ; below by, so a city's average doesn't just grow with TAZ count.
        CityHHTotal[City_i]  = CityHHTotal[City_i]  + HH_i
        CityJobTotal[City_i] = CityJobTotal[City_i] + Job_i

        ;congested auto travel time --------------------------------------------------------------------------
        ;  AM forward / PM transpose, composite peak, GP path (matches 08's convention)
        mw[111] = (mi.1.GP_IVT + mi.2.GP_IVT.T) / 2
        mw[112] = (mi.1.OVT + mi.2.OVT.T) / 2
        mw[110] = mw[111] + mw[112]

        JLOOP EXCLUDE=@dummyzones@, @externalzones@
            if (mw[111]<=0 | mw[111]>=9999)  mw[110] = 9999
        ENDJLOOP


        ;free-flow auto travel time & distance -- feeds the Loss_Cong/Loss_Net
        ;decomposition (see file-header comment). Same convention as
        ;08_Access_to_Opportunity.s's own free-flow calc, just against
        ;MATI[15] (Skm_FF.mtx) instead of its MATI[03].
        mw[121] = (mi.15.GP_IVT + mi.15.GP_IVT.T) / 2
        mw[122] = (mi.15.OVT + mi.15.OVT.T) / 2
        mw[120] = mw[121] + mw[122]
        mw[123] = (mi.15.GP_Dist + mi.15.GP_Dist.T) / 2

        JLOOP EXCLUDE=@dummyzones@, @externalzones@
            if (mw[121]<=0 | mw[121]>=9999)  mw[120] = 9999
            if (mw[123]<=0 | mw[123]>=9999)  mw[123] = 9999
        ENDJLOOP


        ;straight-line distance (miles), from TAZ centroid nodes -- feeds
        ;bike & walk, and (via a running-average free-flow speed, same
        ;convention as 08) the straight-line auto time for Loss_Net.
        JLOOP EXCLUDE=@dummyzones@, @externalzones@
            _diffX = Node_X[i] - Node_X[j]
            _diffY = Node_Y[i] - Node_Y[j]
            mw[133] = sqrt(pow(_diffX, 2) + pow(_diffY, 2)) / 1609.344

            AvgSpeed_Auto_FF = 9999
            if (mw[123]<>9999 & mw[120]<>9999)  AvgSpeed_Auto_FF = mw[123] / mw[120]

            mw[130] = 9999
            if (AvgSpeed_Auto_FF>0 & AvgSpeed_Auto_FF<9999)  mw[130] = mw[133] / AvgSpeed_Auto_FF
        ENDJLOOP

        JLOOP EXCLUDE=@dummyzones@, @externalzones@
            mw[140] = 9999
            mw[150] = 9999
            if (mw[133]<>9999)  mw[140] = mw[133] / @bikespeed@ * 60     ;bike
            if (mw[133]<>9999)  mw[150] = mw[133] / @walkspeed@ * 60     ;walk
        ENDJLOOP


        ;transit travel time (peak service only) -------------------------------------------------------------
        ;walk access
        mw[211] = mi.03.T456789
        mw[212] = mi.04.T456789
        mw[213] = mi.05.T456789
        mw[214] = mi.06.T456789
        mw[215] = mi.07.T456789
        mw[216] = mi.08.T456789

        mw[201] = mw[211] + mi.03.INITWAIT + mi.03.XFERWAIT + mi.03.WALKTIME + mi.03.DRIVETIME
        mw[202] = mw[212] + mi.04.INITWAIT + mi.04.XFERWAIT + mi.04.WALKTIME + mi.04.DRIVETIME
        mw[203] = mw[213] + mi.05.INITWAIT + mi.05.XFERWAIT + mi.05.WALKTIME + mi.05.DRIVETIME
        mw[204] = mw[214] + mi.06.INITWAIT + mi.06.XFERWAIT + mi.06.WALKTIME + mi.06.DRIVETIME
        mw[205] = mw[215] + mi.07.INITWAIT + mi.07.XFERWAIT + mi.07.WALKTIME + mi.07.DRIVETIME
        mw[206] = mw[216] + mi.08.INITWAIT + mi.08.XFERWAIT + mi.08.WALKTIME + mi.08.DRIVETIME

        ;drive access
        mw[261] = mi.09.T456789
        mw[262] = mi.10.T456789
        mw[263] = mi.11.T456789
        mw[264] = mi.12.T456789
        mw[265] = mi.13.T456789
        mw[266] = mi.14.T456789

        mw[251] = mw[261] + mi.09.INITWAIT + mi.09.XFERWAIT + mi.09.WALKTIME + mi.09.DRIVETIME
        mw[252] = mw[262] + mi.10.INITWAIT + mi.10.XFERWAIT + mi.10.WALKTIME + mi.10.DRIVETIME
        mw[253] = mw[263] + mi.11.INITWAIT + mi.11.XFERWAIT + mi.11.WALKTIME + mi.11.DRIVETIME
        mw[254] = mw[264] + mi.12.INITWAIT + mi.12.XFERWAIT + mi.12.WALKTIME + mi.12.DRIVETIME
        mw[255] = mw[265] + mi.13.INITWAIT + mi.13.XFERWAIT + mi.13.WALKTIME + mi.13.DRIVETIME
        mw[256] = mw[266] + mi.14.INITWAIT + mi.14.XFERWAIT + mi.14.WALKTIME + mi.14.DRIVETIME

        JLOOP EXCLUDE=@dummyzones@, @externalzones@
            if (mw[211]<=0 | mw[211]>=9999)  mw[201] = 9999
            if (mw[212]<=0 | mw[212]>=9999)  mw[202] = 9999
            if (mw[213]<=0 | mw[213]>=9999)  mw[203] = 9999
            if (mw[214]<=0 | mw[214]>=9999)  mw[204] = 9999
            if (mw[215]<=0 | mw[215]>=9999)  mw[205] = 9999
            if (mw[216]<=0 | mw[216]>=9999)  mw[206] = 9999

            if (mw[261]<=0 | mw[261]>=9999)  mw[251] = 9999
            if (mw[262]<=0 | mw[262]>=9999)  mw[252] = 9999
            if (mw[263]<=0 | mw[263]>=9999)  mw[253] = 9999
            if (mw[264]<=0 | mw[264]>=9999)  mw[254] = 9999
            if (mw[265]<=0 | mw[265]>=9999)  mw[255] = 9999
            if (mw[266]<=0 | mw[266]>=9999)  mw[256] = 9999

            mw[200] = MIN(mw[201], mw[202], mw[203], mw[204], mw[205], mw[206])
            mw[250] = MIN(mw[251], mw[252], mw[253], mw[254], mw[255], mw[256])
        ENDJLOOP


        ;=====================================================================================================
        ;accumulate into City x City arrays, keyed by CityFlat = (City_i-1)*82+City_j
        ;-- the whole point of this script. See the ARRAY comment above for
        ;why this is a flattened single-subscript index, not [City_i,City_j].
        JLOOP EXCLUDE=@dummyzones@, @externalzones@

            City_j   = CityIdx_by_TAZ[j]
            CityFlat = (City_i - 1) * NUM_CITIES + City_j
            HH_j     = zi.1.TOTHH[j]
            Job_j    = zi.1.TOTEMP[j]
            Retail_j     = zi.1.RETEMP[j]
            Industrial_j = zi.1.INDEMP[j]
            Other_j      = zi.1.OTHEMP[j]

            W_Auto      = ATO_Weight(1, mw[110])
            W_TranWalk  = ATO_Weight(2, mw[200])
            W_TranDrive = ATO_Weight(3, mw[250])
            W_Bike      = ATO_Weight(4, mw[140])
            W_Walk      = ATO_Weight(5, mw[150])

            ; Free-flow and straight-line auto weights -- same decay curve
            ; (curve 1, same as W_Auto), just against free-flow (mw[120]) or
            ; straight-line-derived (mw[130]) travel time instead of
            ; congested (mw[110]). Feeds the Loss_Cong/Loss_Net decomposition
            ; -- see file-header comment.
            W_Auto_FF   = ATO_Weight(1, mw[120])
            W_Auto_SL   = ATO_Weight(1, mw[130])

            ; Weighted by HH_i (households AT the origin i whose access this
            ; is) for every Job/sector column -- see the file-header comment
            ; for why. Job_j/Retail_j/etc. themselves are unweighted; only
            ; the origin-side multiplier is new.
            CityJob_Auto[CityFlat]      = CityJob_Auto[CityFlat]      + W_Auto      * Job_j * HH_i
            CityJob_TranWalk[CityFlat]  = CityJob_TranWalk[CityFlat]  + W_TranWalk  * Job_j * HH_i
            CityJob_TranDrive[CityFlat] = CityJob_TranDrive[CityFlat] + W_TranDrive * Job_j * HH_i
            CityJob_Bike[CityFlat]      = CityJob_Bike[CityFlat]      + W_Bike      * Job_j * HH_i
            CityJob_Walk[CityFlat]      = CityJob_Walk[CityFlat]      + W_Walk      * Job_j * HH_i

            ; Weighted by Job_i (jobs AT i, since HH_j measures labor supply
            ; accessible TO a job at i -- see the file-header comment).
            CityHH_Auto[CityFlat]       = CityHH_Auto[CityFlat]       + W_Auto      * HH_j * Job_i
            CityHH_TranWalk[CityFlat]   = CityHH_TranWalk[CityFlat]   + W_TranWalk  * HH_j * Job_i
            CityHH_TranDrive[CityFlat]  = CityHH_TranDrive[CityFlat]  + W_TranDrive * HH_j * Job_i
            CityHH_Bike[CityFlat]       = CityHH_Bike[CityFlat]       + W_Bike      * HH_j * Job_i
            CityHH_Walk[CityFlat]       = CityHH_Walk[CityFlat]       + W_Walk      * HH_j * Job_i

            ; Free-flow/straight-line auto access sums -- same weighting
            ; pattern as CityJob_Auto/CityHH_Auto above, feeding the
            ; Loss_Cong/Loss_Net decomposition (see file-header comment).
            CityJobAutoFF[CityFlat] = CityJobAutoFF[CityFlat] + W_Auto_FF * Job_j * HH_i
            CityJobAutoSL[CityFlat] = CityJobAutoSL[CityFlat] + W_Auto_SL * Job_j * HH_i
            CityHHAutoFF[CityFlat]  = CityHHAutoFF[CityFlat]  + W_Auto_FF * HH_j * Job_i
            CityHHAutoSL[CityFlat]  = CityHHAutoSL[CityFlat]  + W_Auto_SL * HH_j * Job_i

            ; "Average opportunity time" numerators -- same weighting as
            ; CityJob_*/CityHH_* just above, times this pair's own travel
            ; time (mw[110] auto, mw[200] transit walk-access, mw[250]
            ; transit drive-access, mw[140] bike, mw[150] walk -- all
            ; already computed per-j earlier in this same i-pass, for the
            ; ATO_Weight() lookups above).
            CityJobTimeWt_Auto[CityFlat]      = CityJobTimeWt_Auto[CityFlat]      + W_Auto      * Job_j * HH_i * mw[110]
            CityJobTimeWt_TranWalk[CityFlat]  = CityJobTimeWt_TranWalk[CityFlat]  + W_TranWalk  * Job_j * HH_i * mw[200]
            CityJobTimeWt_TranDrive[CityFlat] = CityJobTimeWt_TranDrive[CityFlat] + W_TranDrive * Job_j * HH_i * mw[250]
            CityJobTimeWt_Bike[CityFlat]      = CityJobTimeWt_Bike[CityFlat]      + W_Bike      * Job_j * HH_i * mw[140]
            CityJobTimeWt_Walk[CityFlat]      = CityJobTimeWt_Walk[CityFlat]      + W_Walk      * Job_j * HH_i * mw[150]

            CityHHTimeWt_Auto[CityFlat]       = CityHHTimeWt_Auto[CityFlat]       + W_Auto      * HH_j * Job_i * mw[110]
            CityHHTimeWt_TranWalk[CityFlat]   = CityHHTimeWt_TranWalk[CityFlat]   + W_TranWalk  * HH_j * Job_i * mw[200]
            CityHHTimeWt_TranDrive[CityFlat]  = CityHHTimeWt_TranDrive[CityFlat]  + W_TranDrive * HH_j * Job_i * mw[250]
            CityHHTimeWt_Bike[CityFlat]       = CityHHTimeWt_Bike[CityFlat]       + W_Bike      * HH_j * Job_i * mw[140]
            CityHHTimeWt_Walk[CityFlat]       = CityHHTimeWt_Walk[CityFlat]       + W_Walk      * HH_j * Job_i * mw[150]

            CityRetail_Auto[CityFlat]      = CityRetail_Auto[CityFlat]      + W_Auto      * Retail_j * HH_i
            CityRetail_TranWalk[CityFlat]  = CityRetail_TranWalk[CityFlat]  + W_TranWalk  * Retail_j * HH_i
            CityRetail_TranDrive[CityFlat] = CityRetail_TranDrive[CityFlat] + W_TranDrive * Retail_j * HH_i
            CityRetail_Bike[CityFlat]      = CityRetail_Bike[CityFlat]      + W_Bike      * Retail_j * HH_i
            CityRetail_Walk[CityFlat]      = CityRetail_Walk[CityFlat]      + W_Walk      * Retail_j * HH_i

            CityIndustrial_Auto[CityFlat]      = CityIndustrial_Auto[CityFlat]      + W_Auto      * Industrial_j * HH_i
            CityIndustrial_TranWalk[CityFlat]  = CityIndustrial_TranWalk[CityFlat]  + W_TranWalk  * Industrial_j * HH_i
            CityIndustrial_TranDrive[CityFlat] = CityIndustrial_TranDrive[CityFlat] + W_TranDrive * Industrial_j * HH_i
            CityIndustrial_Bike[CityFlat]      = CityIndustrial_Bike[CityFlat]      + W_Bike      * Industrial_j * HH_i
            CityIndustrial_Walk[CityFlat]      = CityIndustrial_Walk[CityFlat]      + W_Walk      * Industrial_j * HH_i

            CityOther_Auto[CityFlat]      = CityOther_Auto[CityFlat]      + W_Auto      * Other_j * HH_i
            CityOther_TranWalk[CityFlat]  = CityOther_TranWalk[CityFlat]  + W_TranWalk  * Other_j * HH_i
            CityOther_TranDrive[CityFlat] = CityOther_TranDrive[CityFlat] + W_TranDrive * Other_j * HH_i
            CityOther_Bike[CityFlat]      = CityOther_Bike[CityFlat]      + W_Bike      * Other_j * HH_i
            CityOther_Walk[CityFlat]      = CityOther_Walk[CityFlat]      + W_Walk      * Other_j * HH_i

            ; Per-sector free-flow/straight-line auto access sums -- same
            ; weighting pattern as CityJobAutoFF/SL above, feeding the
            ; per-sector Loss_Cong/Loss_Net decomposition (see file-header
            ; comment). Auto only, same scope as the all-sectors version.
            CityRetailAutoFF[CityFlat]     = CityRetailAutoFF[CityFlat]     + W_Auto_FF * Retail_j     * HH_i
            CityRetailAutoSL[CityFlat]     = CityRetailAutoSL[CityFlat]     + W_Auto_SL * Retail_j     * HH_i
            CityIndustrialAutoFF[CityFlat] = CityIndustrialAutoFF[CityFlat] + W_Auto_FF * Industrial_j * HH_i
            CityIndustrialAutoSL[CityFlat] = CityIndustrialAutoSL[CityFlat] + W_Auto_SL * Industrial_j * HH_i
            CityOtherAutoFF[CityFlat]      = CityOtherAutoFF[CityFlat]      + W_Auto_FF * Other_j      * HH_i
            CityOtherAutoSL[CityFlat]      = CityOtherAutoSL[CityFlat]      + W_Auto_SL * Other_j      * HH_i

            ; Per-sector "average opportunity time" numerators -- same
            ; weighting as CityRetail_*/CityIndustrial_*/CityOther_* just
            ; above, times this pair's own travel time (see the file-header
            ; comment). Lets the app's avg-time stat respond to the Sector
            ; toggle instead of always showing the all-sectors figure.
            CityRetailTimeWt_Auto[CityFlat]      = CityRetailTimeWt_Auto[CityFlat]      + W_Auto      * Retail_j * HH_i * mw[110]
            CityRetailTimeWt_TranWalk[CityFlat]  = CityRetailTimeWt_TranWalk[CityFlat]  + W_TranWalk  * Retail_j * HH_i * mw[200]
            CityRetailTimeWt_TranDrive[CityFlat] = CityRetailTimeWt_TranDrive[CityFlat] + W_TranDrive * Retail_j * HH_i * mw[250]
            CityRetailTimeWt_Bike[CityFlat]      = CityRetailTimeWt_Bike[CityFlat]      + W_Bike      * Retail_j * HH_i * mw[140]
            CityRetailTimeWt_Walk[CityFlat]      = CityRetailTimeWt_Walk[CityFlat]      + W_Walk      * Retail_j * HH_i * mw[150]

            CityIndustrialTimeWt_Auto[CityFlat]      = CityIndustrialTimeWt_Auto[CityFlat]      + W_Auto      * Industrial_j * HH_i * mw[110]
            CityIndustrialTimeWt_TranWalk[CityFlat]  = CityIndustrialTimeWt_TranWalk[CityFlat]  + W_TranWalk  * Industrial_j * HH_i * mw[200]
            CityIndustrialTimeWt_TranDrive[CityFlat] = CityIndustrialTimeWt_TranDrive[CityFlat] + W_TranDrive * Industrial_j * HH_i * mw[250]
            CityIndustrialTimeWt_Bike[CityFlat]      = CityIndustrialTimeWt_Bike[CityFlat]      + W_Bike      * Industrial_j * HH_i * mw[140]
            CityIndustrialTimeWt_Walk[CityFlat]      = CityIndustrialTimeWt_Walk[CityFlat]      + W_Walk      * Industrial_j * HH_i * mw[150]

            CityOtherTimeWt_Auto[CityFlat]      = CityOtherTimeWt_Auto[CityFlat]      + W_Auto      * Other_j * HH_i * mw[110]
            CityOtherTimeWt_TranWalk[CityFlat]  = CityOtherTimeWt_TranWalk[CityFlat]  + W_TranWalk  * Other_j * HH_i * mw[200]
            CityOtherTimeWt_TranDrive[CityFlat] = CityOtherTimeWt_TranDrive[CityFlat] + W_TranDrive * Other_j * HH_i * mw[250]
            CityOtherTimeWt_Bike[CityFlat]      = CityOtherTimeWt_Bike[CityFlat]      + W_Bike      * Other_j * HH_i * mw[140]
            CityOtherTimeWt_Walk[CityFlat]      = CityOtherTimeWt_Walk[CityFlat]      + W_Walk      * Other_j * HH_i * mw[150]

        ENDJLOOP

    endif  ;!(i=dummyzones,externalzones)


    ;=========================================================================================================
    ;dump the finished City x City tables once, after the last zone -- not per-i like 08.
    ;Placed outside the dummy/external exclusion above so it still fires even if the
    ;numerically-last zone happens to be a dummy/external one.
    if (i=@UsedZones@)

        PRINT PRINTO=1,
            CSV=T,
            LIST='HomeCityIdx', 'WorkCityIdx',
                 'Job_Auto', 'Job_TranWalk', 'Job_TranDrive', 'Job_Bike', 'Job_Walk',
                 'HH_Auto',  'HH_TranWalk',  'HH_TranDrive',  'HH_Bike',  'HH_Walk',
                 'JobTimeWt_Auto', 'JobTimeWt_TranWalk', 'JobTimeWt_TranDrive', 'JobTimeWt_Bike', 'JobTimeWt_Walk',
                 'HHTimeWt_Auto',  'HHTimeWt_TranWalk',  'HHTimeWt_TranDrive',  'HHTimeWt_Bike',  'HHTimeWt_Walk',
                 'JobAutoFF', 'JobAutoSL', 'HHAutoFF', 'HHAutoSL',
                 'Retail_Auto',     'Retail_TranWalk',     'Retail_TranDrive',     'Retail_Bike',     'Retail_Walk',
                 'Industrial_Auto', 'Industrial_TranWalk', 'Industrial_TranDrive', 'Industrial_Bike', 'Industrial_Walk',
                 'Other_Auto',      'Other_TranWalk',      'Other_TranDrive',      'Other_Bike',      'Other_Walk',
                 'RetailTimeWt_Auto',     'RetailTimeWt_TranWalk',     'RetailTimeWt_TranDrive',     'RetailTimeWt_Bike',     'RetailTimeWt_Walk',
                 'IndustrialTimeWt_Auto', 'IndustrialTimeWt_TranWalk', 'IndustrialTimeWt_TranDrive', 'IndustrialTimeWt_Bike', 'IndustrialTimeWt_Walk',
                 'OtherTimeWt_Auto',      'OtherTimeWt_TranWalk',      'OtherTimeWt_TranDrive',      'OtherTimeWt_Bike',      'OtherTimeWt_Walk',
                 'RetailAutoFF', 'RetailAutoSL', 'IndustrialAutoFF', 'IndustrialAutoSL', 'OtherAutoFF', 'OtherAutoSL'

        LOOP CityA = 1, NUM_CITIES
            LOOP CityB = 1, NUM_CITIES
                DumpFlat = (CityA - 1) * NUM_CITIES + CityB
                PRINT PRINTO=1,
                    CSV=T,
                    FORM=10.2,
                    LIST=CityA, CityB,
                         ROUND(CityJob_Auto[DumpFlat]     ),
                         ROUND(CityJob_TranWalk[DumpFlat] ),
                         ROUND(CityJob_TranDrive[DumpFlat]),
                         ROUND(CityJob_Bike[DumpFlat]     ),
                         ROUND(CityJob_Walk[DumpFlat]     ),
                         ROUND(CityHH_Auto[DumpFlat]      ),
                         ROUND(CityHH_TranWalk[DumpFlat]  ),
                         ROUND(CityHH_TranDrive[DumpFlat] ),
                         ROUND(CityHH_Bike[DumpFlat]      ),
                         ROUND(CityHH_Walk[DumpFlat]      ),
                         ROUND(CityJobTimeWt_Auto[DumpFlat]     ),
                         ROUND(CityJobTimeWt_TranWalk[DumpFlat] ),
                         ROUND(CityJobTimeWt_TranDrive[DumpFlat]),
                         ROUND(CityJobTimeWt_Bike[DumpFlat]     ),
                         ROUND(CityJobTimeWt_Walk[DumpFlat]     ),
                         ROUND(CityHHTimeWt_Auto[DumpFlat]      ),
                         ROUND(CityHHTimeWt_TranWalk[DumpFlat]  ),
                         ROUND(CityHHTimeWt_TranDrive[DumpFlat] ),
                         ROUND(CityHHTimeWt_Bike[DumpFlat]      ),
                         ROUND(CityHHTimeWt_Walk[DumpFlat]      ),
                         ROUND(CityJobAutoFF[DumpFlat]),
                         ROUND(CityJobAutoSL[DumpFlat]),
                         ROUND(CityHHAutoFF[DumpFlat] ),
                         ROUND(CityHHAutoSL[DumpFlat] ),
                         ROUND(CityRetail_Auto[DumpFlat]        ),
                         ROUND(CityRetail_TranWalk[DumpFlat]    ),
                         ROUND(CityRetail_TranDrive[DumpFlat]   ),
                         ROUND(CityRetail_Bike[DumpFlat]        ),
                         ROUND(CityRetail_Walk[DumpFlat]        ),
                         ROUND(CityIndustrial_Auto[DumpFlat]    ),
                         ROUND(CityIndustrial_TranWalk[DumpFlat]),
                         ROUND(CityIndustrial_TranDrive[DumpFlat]),
                         ROUND(CityIndustrial_Bike[DumpFlat]    ),
                         ROUND(CityIndustrial_Walk[DumpFlat]    ),
                         ROUND(CityOther_Auto[DumpFlat]         ),
                         ROUND(CityOther_TranWalk[DumpFlat]     ),
                         ROUND(CityOther_TranDrive[DumpFlat]    ),
                         ROUND(CityOther_Bike[DumpFlat]         ),
                         ROUND(CityOther_Walk[DumpFlat]         ),
                         ROUND(CityRetailTimeWt_Auto[DumpFlat]        ),
                         ROUND(CityRetailTimeWt_TranWalk[DumpFlat]    ),
                         ROUND(CityRetailTimeWt_TranDrive[DumpFlat]   ),
                         ROUND(CityRetailTimeWt_Bike[DumpFlat]        ),
                         ROUND(CityRetailTimeWt_Walk[DumpFlat]        ),
                         ROUND(CityIndustrialTimeWt_Auto[DumpFlat]    ),
                         ROUND(CityIndustrialTimeWt_TranWalk[DumpFlat]),
                         ROUND(CityIndustrialTimeWt_TranDrive[DumpFlat]),
                         ROUND(CityIndustrialTimeWt_Bike[DumpFlat]    ),
                         ROUND(CityIndustrialTimeWt_Walk[DumpFlat]    ),
                         ROUND(CityOtherTimeWt_Auto[DumpFlat]         ),
                         ROUND(CityOtherTimeWt_TranWalk[DumpFlat]     ),
                         ROUND(CityOtherTimeWt_TranDrive[DumpFlat]    ),
                         ROUND(CityOtherTimeWt_Bike[DumpFlat]         ),
                         ROUND(CityOtherTimeWt_Walk[DumpFlat]         ),
                         ROUND(CityRetailAutoFF[DumpFlat]    ),
                         ROUND(CityRetailAutoSL[DumpFlat]    ),
                         ROUND(CityIndustrialAutoFF[DumpFlat]),
                         ROUND(CityIndustrialAutoSL[DumpFlat]),
                         ROUND(CityOtherAutoFF[DumpFlat]     ),
                         ROUND(CityOtherAutoSL[DumpFlat]     )
            ENDLOOP
        ENDLOOP

        ; Second output: per-city HH/Job totals -- the denominators the app
        ; divides the weighted CityDetail table above by.
        PRINT PRINTO=2,
            CSV=T,
            LIST='CityIdx', 'TotalHH', 'TotalJob'

        LOOP CityOnly = 1, NUM_CITIES
            PRINT PRINTO=2,
                CSV=T,
                FORM=10.2,
                LIST=CityOnly,
                     ROUND(CityHHTotal[CityOnly] ),
                     ROUND(CityJobTotal[CityOnly])
        ENDLOOP

    endif  ;i=@UsedZones@

ENDRUN


;get end time and report run time
ScriptEndTime = currenttime()
*(ECHO Access to Opportunity (City Detail) complete >> access_to_opportunity_detail.txt)

// RayValidator.cpp — Minimal test study for V4 SG 12/13 ray reference data
// Purpose: Reads V4 DemandRayPrice (SG 12) and SupplyRayPrice (SG 13) from
//          all TF charts via cross-chart reference (same pattern as ZTE/ZB4/ZRA),
//          writes every non-zero value to a reference CSV.
//          Used to validate ZoneTouchEngine's ray accumulator output.
// Version: 1.1 (2026-03-23) — cross-chart multi-TF, matches ZTE input layout
// Usage:   Deploy on the 250-vol base chart. Chart slot inputs match ZTE defaults.
//          On full recalc, writes ray_reference.csv.

#include "sierrachart.h"

SCDLLName("Ray Validator")

constexpr int V4_SG_DEMAND_RAY_PRICE = 12;
constexpr int V4_SG_SUPPLY_RAY_PRICE = 13;
constexpr int V4_SG_DEMAND_BROKEN    = 6;
constexpr int V4_SG_SUPPLY_BROKEN    = 7;
constexpr int MAX_CHART_SLOTS        = 9;

// Source label from chart bar period (same logic as ZTE)
static const char* GetSourceLabel(SCStudyInterfaceRef sc, int chartNumber)
{
    n_ACSIL::s_BarPeriod bp;
    sc.GetBarPeriodParametersForChart(chartNumber, bp);
    int mins = bp.IntradayChartBarPeriodParameter1 / 60;
    if (mins >= 720) return "720m"; if (mins >= 480) return "480m";
    if (mins >= 360) return "360m"; if (mins >= 240) return "240m";
    if (mins >= 120) return "120m"; if (mins >= 90)  return "90m";
    if (mins >= 60)  return "60m";  if (mins >= 30)  return "30m";
    if (mins >= 15)  return "15m";  return "??m";
}

SCSFExport scsf_RayValidator(SCStudyInterfaceRef sc)
{
    // Input layout matches ZTE: Input[0] = active count, Input[1+s*2] = chart#, Input[2+s*2] = studyID
    SCInputRef InputActiveCount = sc.Input[0];
    // Input[1-18]: 9 chart slots × 2
    SCInputRef InputCSVPath     = sc.Input[19];

    if (sc.SetDefaults)
    {
        sc.GraphName = "Ray Validator [v1.1]";
        sc.StudyDescription = "Multi-TF cross-chart V4 SG 12/13 ray reference exporter";
        sc.AutoLoop = 1;
        sc.GraphRegion = 0;
        sc.FreeDLL = 0;
        sc.CalculationPrecedence = LOW_PREC_LEVEL;

        InputActiveCount.Name = "Active Chart Count";
        InputActiveCount.SetInt(9);
        InputActiveCount.SetIntLimits(1, 9);

        // Chart slot defaults — identical to ZTE
        static const int chartDefaults[9] = {3,4,5,6,7,2,8,14,9};
        static const int studyDefaults[9] = {1,3,2,3,1,4,3,2,2};
        for (int s = 0; s < 9; s++)
        {
            int base = 1 + s * 2;
            SCString numName, idName;
            numName.Format("Chart %d Number (0=off)", s + 1);
            idName.Format("Chart %d V4 Study ID", s + 1);
            sc.Input[base].Name = numName;
            sc.Input[base].SetInt(chartDefaults[s]);
            sc.Input[base].SetIntLimits(0, 500);
            sc.Input[base + 1].Name = idName;
            sc.Input[base + 1].SetInt(studyDefaults[s]);
            sc.Input[base + 1].SetIntLimits(1, 500);
        }

        InputCSVPath.Name = "CSV Output Path";
        InputCSVPath.SetPathAndFileName(
            "C:\\Projects\\sierrachart\\analysis\\analyzer_zonereaction\\ray_reference.csv");

        return;
    }

    // Only write CSV on the last bar of a full recalc
    if (sc.Index != sc.ArraySize - 1)
        return;

    int activeCount = InputActiveCount.GetInt();
    if (activeCount < 1) activeCount = 1;
    if (activeCount > MAX_CHART_SLOTS) activeCount = MAX_CHART_SLOTS;

    FILE* fp = fopen(InputCSVPath.GetPathAndFileName(), "w");
    if (fp == nullptr)
    {
        sc.AddMessageToLog("RayValidator: Cannot open output CSV", 1);
        return;
    }

    fprintf(fp, "BaseBarIndex,DateTime,ChartSlot,SourceLabel,ChartNumber,"
                "HtfBarIndex,DemandRayPrice,SupplyRayPrice,"
                "DemandBrokenCount,SupplyBrokenCount\n");

    int totalRows = 0;
    int baseArraySize = sc.ArraySize;

    for (int s = 0; s < activeCount; s++)
    {
        int inputBase = 1 + s * 2;
        int chartNum = sc.Input[inputBase].GetInt();
        int studyID  = sc.Input[inputBase + 1].GetInt();
        if (chartNum == 0) continue;

        SCFloatArray DemandRay, SupplyRay, DemandBroken, SupplyBroken;
        sc.GetStudyArrayFromChartUsingID(chartNum, studyID, V4_SG_DEMAND_RAY_PRICE, DemandRay);
        sc.GetStudyArrayFromChartUsingID(chartNum, studyID, V4_SG_SUPPLY_RAY_PRICE, SupplyRay);
        sc.GetStudyArrayFromChartUsingID(chartNum, studyID, V4_SG_DEMAND_BROKEN, DemandBroken);
        sc.GetStudyArrayFromChartUsingID(chartNum, studyID, V4_SG_SUPPLY_BROKEN, SupplyBroken);

        int htfSize = DemandRay.GetArraySize();
        if (htfSize == 0) continue;

        const char* srcLabel = GetSourceLabel(sc, chartNum);

        // Iterate over base chart bars, map to HTF bar, check for rays
        for (int bi = 0; bi < baseArraySize; bi++)
        {
            int htfIdx = sc.GetNearestMatchForDateTimeIndex(chartNum, bi);
            if (htfIdx < 0 || htfIdx >= htfSize) continue;

            float demRay = DemandRay[htfIdx];
            float supRay = SupplyRay[htfIdx];

            if (demRay == 0.0f && supRay == 0.0f) continue;

            // Dedup: only emit on the first base bar that maps to this HTF bar
            if (bi > 0)
            {
                int prevHtfIdx = sc.GetNearestMatchForDateTimeIndex(chartNum, bi - 1);
                if (prevHtfIdx == htfIdx) continue;
            }

            SCDateTime dt = sc.BaseDateTimeIn[bi];
            int yr, mo, dy, hr, mn, sc2;
            dt.GetDateTimeYMDHMS(yr, mo, dy, hr, mn, sc2);

            float demBrk = (DemandBroken.GetArraySize() > htfIdx) ? DemandBroken[htfIdx] : 0.0f;
            float supBrk = (SupplyBroken.GetArraySize() > htfIdx) ? SupplyBroken[htfIdx] : 0.0f;

            fprintf(fp, "%d,%04d-%02d-%02d %02d:%02d:%02d,%d,%s,%d,%d,%.2f,%.2f,%.0f,%.0f\n",
                    bi, yr, mo, dy, hr, mn, sc2,
                    s, srcLabel, chartNum, htfIdx,
                    demRay, supRay, demBrk, supBrk);
            totalRows++;
        }
    }

    fclose(fp);

    SCString msg;
    msg.Format("RayValidator: Wrote %d ray events across %d TF slots (%d base bars)",
               totalRows, activeCount, baseArraySize);
    sc.AddMessageToLog(msg, 0);
}

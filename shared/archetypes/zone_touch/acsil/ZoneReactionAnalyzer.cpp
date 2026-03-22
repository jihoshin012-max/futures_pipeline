// STUDY VERSION LOG
// Current: v3.2 (2026-03-22) — VP proximity filter added
// Prior:   v3.1 (2026-03-07) — Pipeline snapshot, pre-VP fix
// Backup:  ZoneReactionAnalyzer_v31.cpp

// @study: Zone Reaction Analyzer
// @version: 2
// @author: ATEAM
// @summary: Multi-TF zone reaction analyzer. Reads V4 zone data from up to 9
//           timeframe charts, detects all touch types (edge, interior, VP ray),
//           tracks reaction/penetration over a configurable observation window,
//           and exports a single unified CSV with per-timeframe labels.

#include "sierrachart.h"

SCDLLName("Zone Reaction Analyzer")

// === CONSTANTS ===

constexpr int      MAX_TRACKED_TOUCHES  = 20000;
constexpr int      MAX_TRACKED_ZONES    = 10000;
constexpr uint32_t TOUCH_STORAGE_MAGIC  = 0x5A524156; // "ZRAV" v3 + threshold bars
constexpr int      MAX_CHART_SLOTS      = 9;
constexpr int      EVICT_FRACTION       = 2;

constexpr int V4_SG_DEMAND_BROKEN      = 6;
constexpr int V4_SG_SUPPLY_BROKEN      = 7;
constexpr int V4_SG_NEAREST_DEMAND_TOP = 8;
constexpr int V4_SG_NEAREST_DEMAND_BOT = 9;
constexpr int V4_SG_NEAREST_SUPPLY_TOP = 10;
constexpr int V4_SG_NEAREST_SUPPLY_BOT = 11;
constexpr int V4_SG_VP_IMBALANCE_PRICE = 14;

constexpr int DEBOUNCE_TICKS           = 3;
constexpr int DEBOUNCE_BAR_WINDOW      = 20;
constexpr int APPROACH_VELOCITY_LOOKBACK = 10;
constexpr int TREND_LOOKBACK           = 50;

// Threshold-crossing bar tracking (for deterministic backtest resolution)
constexpr int   NUM_RXN_THRESHOLDS = 7;
constexpr int   NUM_PEN_THRESHOLDS = 4;
constexpr float RXN_THRESHOLDS[NUM_RXN_THRESHOLDS] = {30, 50, 80, 120, 160, 240, 360};
constexpr float PEN_THRESHOLDS[NUM_PEN_THRESHOLDS]  = {30, 50, 80, 120};

// === ENUMS ===

enum TouchType
{
    kDemandEdge = 0,
    kSupplyEdge,
    kVPRay,
    kTouchTypeCount
};

enum PersistentStorage
{
    kTouchStoragePtr = 0
};

// === DATA STRUCTURES ===

// Per-bar scratch data for one chart slot (not persisted)
struct ChartSlotData
{
    int  ChartNumber;
    int  StudyID;
    char Label[32];
    SCFloatArray DemandTop, DemandBot, SupplyTop, SupplyBot;
    SCFloatArray VPImbalance, DemandBroken, SupplyBroken;
    int  V4Size;
    int  V4Idx;
    int  V4Idx1;
    bool Valid;
};

struct TrackedZone
{
    float Top;
    float Bot;
    int   FirstSeenBar;
    int   TouchCount;
    int   SourceChart;
    bool  IsDemand;
};

struct TrackedTouch
{
    int   TouchBarIndex;
    float TouchPrice;
    int   Type;
    int   ApproachDir;
    float ZoneTop;
    float ZoneBot;
    float VPRayPrice;
    float Reaction;
    float Penetration;
    float ApproachVelocity;
    float TrendSlope;
    int   ReactionPeakBar;
    int   ResolutionBar;
    int   TouchSequence;
    int   ZoneAgeBars;
    int   SourceChart;
    int   SourceStudyID;
    int   SourceSlotIdx;
    char  SourceLabel[32];
    int   RxnCrossBar[7];   // first bar where reaction >= threshold, -1 = never
    int   PenCrossBar[4];   // first bar where penetration >= threshold, -1 = never
    int   BreakBarIndex;
    bool  HasVPRay;
    bool  ZoneBroken;
    bool  Resolved;
    bool  Active;
};

struct TouchStorage
{
    uint32_t     MagicNumber;
    int          TouchCount;
    int          ZoneCount;
    TrackedTouch Touches[MAX_TRACKED_TOUCHES];
    TrackedZone  Zones[MAX_TRACKED_ZONES];
};

// Chart slot defaults
struct ChartDefault { int chartNum; int studyID; const char* label; };
static const ChartDefault CHART_DEFAULTS[MAX_CHART_SLOTS] = {
    { 3,  1, "15m"  },
    { 4,  3, "30m"  },
    { 5,  2, "60m"  },
    { 6,  3, "90m"  },
    { 7,  1, "120m" },
    { 2,  4, "240m" },
    { 8,  3, "360m" },
    { 14, 2, "480m" },
    { 9,  2, "720m" },
};

// === HELPER: Allocate or validate persistent storage ===

static TouchStorage* GetOrAllocateStorage(SCStudyInterfaceRef sc)
{
    TouchStorage* p = (TouchStorage*)sc.GetPersistentPointer(kTouchStoragePtr);

    if (p == nullptr || p->MagicNumber != TOUCH_STORAGE_MAGIC)
    {
        if (p != nullptr)
            sc.FreeMemory(p);

        p = (TouchStorage*)sc.AllocateMemory(sizeof(TouchStorage));
        if (p == nullptr)
            return nullptr;

        memset(p, 0, sizeof(TouchStorage));
        p->MagicNumber = TOUCH_STORAGE_MAGIC;
        sc.SetPersistentPointer(kTouchStoragePtr, p);
    }

    return p;
}

// === HELPER: Evict oldest touches when full ===

static void EvictOldTouches(TouchStorage* p)
{
    int evictCount = p->TouchCount / EVICT_FRACTION;
    if (evictCount < 1) evictCount = 1;

    // Force-resolve evicted touches so their data is preserved in CSV
    for (int i = 0; i < evictCount; i++)
    {
        TrackedTouch& t = p->Touches[i];
        if (t.Active && !t.Resolved)
        {
            t.Resolved = true;
            t.ResolutionBar = t.TouchBarIndex;
        }
    }

    int remaining = p->TouchCount - evictCount;
    memmove(&p->Touches[0], &p->Touches[evictCount], remaining * sizeof(TrackedTouch));
    memset(&p->Touches[remaining], 0, evictCount * sizeof(TrackedTouch));
    p->TouchCount = remaining;
}

// === HELPER: Evict oldest zones when full ===

static void EvictOldZones(TouchStorage* p)
{
    int evictCount = p->ZoneCount / EVICT_FRACTION;
    if (evictCount < 1) evictCount = 1;

    int remaining = p->ZoneCount - evictCount;
    memmove(&p->Zones[0], &p->Zones[evictCount], remaining * sizeof(TrackedZone));
    memset(&p->Zones[remaining], 0, evictCount * sizeof(TrackedZone));
    p->ZoneCount = remaining;
}

// === HELPER: Find or create a tracked zone ===
// Zones are keyed by (top, bot, isDemand, sourceChart) — per-TF identity.

static int FindOrCreateZone(TouchStorage* p, float top, float bot,
                            bool isDemand, int sourceChart, int barIndex)
{
    for (int i = 0; i < p->ZoneCount; i++)
    {
        if (p->Zones[i].IsDemand == isDemand &&
            p->Zones[i].SourceChart == sourceChart &&
            fabs(p->Zones[i].Top - top) < 0.01f &&
            fabs(p->Zones[i].Bot - bot) < 0.01f)
            return i;
    }

    if (p->ZoneCount >= MAX_TRACKED_ZONES)
        EvictOldZones(p);

    int idx = p->ZoneCount;
    p->Zones[idx].Top          = top;
    p->Zones[idx].Bot          = bot;
    p->Zones[idx].FirstSeenBar = barIndex;
    p->Zones[idx].TouchCount   = 0;
    p->Zones[idx].SourceChart  = sourceChart;
    p->Zones[idx].IsDemand     = isDemand;
    p->ZoneCount++;
    return idx;
}

// === HELPER: Debounce duplicate touches ===
// Only debounce within the same source chart and within a bar window.

static bool IsDebouncedDuplicate(TouchStorage* p, int type, float price,
                                  float tickSize, int currentBar, int sourceChart)
{
    float threshold = DEBOUNCE_TICKS * tickSize;
    for (int i = p->TouchCount - 1; i >= 0; i--)
    {
        TrackedTouch& t = p->Touches[i];
        if (!t.Active)
            continue;
        if (currentBar - t.TouchBarIndex > DEBOUNCE_BAR_WINDOW)
            break;
        if (t.SourceChart == sourceChart &&
            t.Type == type && fabs(t.TouchPrice - price) < threshold)
            return true;
    }
    return false;
}

// === HELPER: Calculate approach velocity ===

static float CalcApproachVelocity(SCStudyInterfaceRef sc, int barIndex, float tickSize)
{
    if (barIndex < APPROACH_VELOCITY_LOOKBACK)
        return 0.0f;
    float priceNow  = sc.BaseData[SC_LAST][barIndex];
    float pricePrev = sc.BaseData[SC_LAST][barIndex - APPROACH_VELOCITY_LOOKBACK];
    return (priceNow - pricePrev) / tickSize;
}

// === HELPER: Calculate trend slope ===

static float CalcTrendSlope(SCStudyInterfaceRef sc, int barIndex, float tickSize)
{
    if (barIndex < TREND_LOOKBACK)
        return 0.0f;
    float priceNow  = sc.BaseData[SC_LAST][barIndex];
    float pricePrev = sc.BaseData[SC_LAST][barIndex - TREND_LOOKBACK];
    return (priceNow - pricePrev) / tickSize;
}

// === HELPER: Add a tracked touch ===

static int AddTouch(TouchStorage* p, int barIndex, float touchPrice, int type,
                    int approachDir, float zoneTop, float zoneBot,
                    bool hasVPRay, float vpRayPrice,
                    int touchSequence, int zoneAgeBars,
                    float approachVelocity, float trendSlope,
                    int sourceChart, int sourceStudyID,
                    int sourceSlotIdx, const char* sourceLabel)
{
    if (p->TouchCount >= MAX_TRACKED_TOUCHES)
        EvictOldTouches(p);
    if (p->TouchCount >= MAX_TRACKED_TOUCHES)
        return -1;

    int idx = p->TouchCount;
    TrackedTouch& t = p->Touches[idx];

    t.TouchBarIndex    = barIndex;
    t.TouchPrice       = touchPrice;
    t.Type             = type;
    t.ApproachDir      = approachDir;
    t.ZoneTop          = zoneTop;
    t.ZoneBot          = zoneBot;
    t.VPRayPrice       = vpRayPrice;
    t.HasVPRay         = hasVPRay;
    t.Reaction         = 0.0f;
    t.Penetration      = 0.0f;
    t.ReactionPeakBar  = barIndex;
    t.ZoneBroken       = false;
    t.BreakBarIndex    = -1;
    t.Resolved         = false;
    t.ResolutionBar    = -1;
    t.Active           = true;
    t.TouchSequence    = touchSequence;
    t.ZoneAgeBars      = zoneAgeBars;
    t.ApproachVelocity = approachVelocity;
    t.TrendSlope       = trendSlope;
    t.SourceChart      = sourceChart;
    t.SourceStudyID    = sourceStudyID;
    t.SourceSlotIdx    = sourceSlotIdx;
    strncpy(t.SourceLabel, sourceLabel, 31);
    t.SourceLabel[31]  = '\0';

    for (int th = 0; th < NUM_RXN_THRESHOLDS; th++) t.RxnCrossBar[th] = -1;
    for (int th = 0; th < NUM_PEN_THRESHOLDS; th++) t.PenCrossBar[th] = -1;

    p->TouchCount++;
    return idx;
}

// === HELPER: Touch type to string ===

static const char* TouchTypeStr(int type)
{
    switch (type)
    {
        case kDemandEdge:     return "DEMAND_EDGE";
        case kSupplyEdge:     return "SUPPLY_EDGE";
        case kVPRay:          return "VP_RAY";
        default:              return "UNKNOWN";
    }
}

// === HELPER: Fetch V4 arrays for a chart slot ===

static void FetchChartSlot(SCStudyInterfaceRef sc, ChartSlotData& slot, int index)
{
    slot.Valid = false;

    if (slot.ChartNumber == 0)
        return;

    sc.GetStudyArrayFromChartUsingID(slot.ChartNumber, slot.StudyID,
                                     V4_SG_NEAREST_DEMAND_TOP, slot.DemandTop);
    sc.GetStudyArrayFromChartUsingID(slot.ChartNumber, slot.StudyID,
                                     V4_SG_NEAREST_DEMAND_BOT, slot.DemandBot);
    sc.GetStudyArrayFromChartUsingID(slot.ChartNumber, slot.StudyID,
                                     V4_SG_NEAREST_SUPPLY_TOP, slot.SupplyTop);
    sc.GetStudyArrayFromChartUsingID(slot.ChartNumber, slot.StudyID,
                                     V4_SG_NEAREST_SUPPLY_BOT, slot.SupplyBot);
    sc.GetStudyArrayFromChartUsingID(slot.ChartNumber, slot.StudyID,
                                     V4_SG_VP_IMBALANCE_PRICE, slot.VPImbalance);
    sc.GetStudyArrayFromChartUsingID(slot.ChartNumber, slot.StudyID,
                                     V4_SG_DEMAND_BROKEN, slot.DemandBroken);
    sc.GetStudyArrayFromChartUsingID(slot.ChartNumber, slot.StudyID,
                                     V4_SG_SUPPLY_BROKEN, slot.SupplyBroken);

    if (slot.DemandTop.GetArraySize() == 0 || slot.SupplyTop.GetArraySize() == 0)
        return;

    slot.V4Size = slot.DemandTop.GetArraySize();
    slot.V4Idx  = sc.GetNearestMatchForDateTimeIndex(slot.ChartNumber, index);
    slot.V4Idx1 = sc.GetNearestMatchForDateTimeIndex(slot.ChartNumber, index - 1);

    if (slot.V4Idx < 0 || slot.V4Idx >= slot.V4Size ||
        slot.V4Idx1 < 0 || slot.V4Idx1 >= slot.V4Size)
        return;

    slot.Valid = true;
}

// === HELPER: Write CSV ===

static void WriteCSV(SCStudyInterfaceRef sc, TouchStorage* p,
                     const SCString& customFolder)
{
    SCString filePath;
    SCString fileName("ZoneReactionAnalysis_MultiTF.csv");

    if (customFolder.GetLength() > 0)
    {
        filePath = customFolder;
        if (filePath[filePath.GetLength() - 1] != '\\' &&
            filePath[filePath.GetLength() - 1] != '/')
            filePath += "\\";
        filePath += fileName;
    }
    else
    {
        filePath.Format("%s%s", sc.DataFilesFolder().GetChars(),
                        fileName.GetChars());
    }

    int fileHandle = 0;
    sc.OpenFile(filePath, n_ACSIL::FILE_MODE_OPEN_TO_REWRITE_FROM_START, fileHandle);
    if (fileHandle == 0)
        return;

    SCString header(
        "DateTime,BarIndex,TouchType,ApproachDir,TouchPrice,ZoneTop,ZoneBot,"
        "HasVPRay,VPRayPrice,Reaction,Penetration,ReactionPeakBar,"
        "ZoneBroken,BreakBarIndex,BarsObserved,TouchSequence,ZoneAgeBars,ApproachVelocity,"
        "TrendSlope,SourceChart,SourceStudyID,SourceLabel,"
        "RxnBar_30,RxnBar_50,RxnBar_80,RxnBar_120,RxnBar_160,RxnBar_240,RxnBar_360,"
        "PenBar_30,PenBar_50,PenBar_80,PenBar_120\r\n");
    unsigned int bytesWritten = 0;
    sc.WriteFile(fileHandle, header.GetChars(), header.GetLength(), &bytesWritten);

    for (int i = 0; i < p->TouchCount; i++)
    {
        TrackedTouch& t = p->Touches[i];
        if (!t.Active)
            continue;

        SCDateTime barDT = sc.BaseDateTimeIn[t.TouchBarIndex];
        int year, month, day, hour, minute, second;
        barDT.GetDateTimeYMDHMS(year, month, day, hour, minute, second);

        int barsObserved = t.Resolved ? (t.ResolutionBar - t.TouchBarIndex) : -1;

        SCString row;
        row.Format("%04d-%02d-%02d %02d:%02d:%02d,%d,%s,%d,%.2f,%.2f,%.2f,%d,%.2f,"
                   "%.1f,%.1f,%d,%d,%d,%d,%d,%d,%.1f,%.1f,%d,%d,%s,"
                   "%d,%d,%d,%d,%d,%d,%d,%d,%d,%d,%d\r\n",
                   year, month, day, hour, minute, second,
                   t.TouchBarIndex,
                   TouchTypeStr(t.Type),
                   t.ApproachDir,
                   t.TouchPrice,
                   t.ZoneTop,
                   t.ZoneBot,
                   t.HasVPRay ? 1 : 0,
                   t.VPRayPrice,
                   t.Reaction,
                   t.Penetration,
                   t.ReactionPeakBar,
                   t.ZoneBroken ? 1 : 0,
                   t.BreakBarIndex,
                   barsObserved,
                   t.TouchSequence,
                   t.ZoneAgeBars,
                   t.ApproachVelocity,
                   t.TrendSlope,
                   t.SourceChart,
                   t.SourceStudyID,
                   t.SourceLabel,
                   t.RxnCrossBar[0], t.RxnCrossBar[1], t.RxnCrossBar[2],
                   t.RxnCrossBar[3], t.RxnCrossBar[4], t.RxnCrossBar[5],
                   t.RxnCrossBar[6],
                   t.PenCrossBar[0], t.PenCrossBar[1], t.PenCrossBar[2],
                   t.PenCrossBar[3]);

        sc.WriteFile(fileHandle, row.GetChars(), row.GetLength(), &bytesWritten);
    }

    sc.CloseFile(fileHandle);

    SCString logMsg;
    logMsg.Format("ZRA: CSV written to: %s (%d touches)",
                  filePath.GetChars(), p->TouchCount);
    sc.AddMessageToLog(logMsg, 1);
}

// === HELPER: Log summary stats ===

static void LogSummary(SCStudyInterfaceRef sc, TouchStorage* p)
{
    int   count[kTouchTypeCount]          = {};
    float reactionSum[kTouchTypeCount]    = {};
    float penetrationSum[kTouchTypeCount] = {};
    int   brokenCount[kTouchTypeCount]    = {};
    int   totalResolved = 0;

    for (int i = 0; i < p->TouchCount; i++)
    {
        TrackedTouch& t = p->Touches[i];
        if (!t.Active || !t.Resolved)
            continue;

        totalResolved++;
        int ty = t.Type;
        if (ty < 0 || ty >= kTouchTypeCount)
            continue;

        count[ty]++;
        reactionSum[ty]    += t.Reaction;
        penetrationSum[ty] += t.Penetration;
        if (t.ZoneBroken) brokenCount[ty]++;
    }

    auto avg = [](float sum, int cnt) -> float {
        return (cnt > 0) ? (sum / cnt) : 0.0f;
    };

    SCString msg;
    msg.Format("=== Zone Reaction Analysis (Multi-TF, %d touches, %d resolved) ===",
               p->TouchCount, totalResolved);
    sc.AddMessageToLog(msg, 0);

    const char* typeNames[] = {
        "DEMAND_EDGE", "SUPPLY_EDGE", "VP_RAY"
    };

    for (int ty = 0; ty < kTouchTypeCount; ty++)
    {
        if (count[ty] == 0)
            continue;
        msg.Format("  %s: %d | AvgR: %.1f | AvgP: %.1f | Broken: %d",
                   typeNames[ty], count[ty],
                   avg(reactionSum[ty], count[ty]),
                   avg(penetrationSum[ty], count[ty]),
                   brokenCount[ty]);
        sc.AddMessageToLog(msg, 0);
    }
}


// === MAIN STUDY FUNCTION ===

SCSFExport scsf_ZoneReactionAnalyzer(SCStudyInterfaceRef sc)
{
    // --- Subgraph references ---
    SCSubgraphRef SG_DemandEdge     = sc.Subgraph[0];
    SCSubgraphRef SG_SupplyEdge     = sc.Subgraph[1];
    SCSubgraphRef SG_VPRayTouch     = sc.Subgraph[2];
    SCSubgraphRef SG_Reaction       = sc.Subgraph[3];
    SCSubgraphRef SG_Penetration    = sc.Subgraph[4];

    // === SET DEFAULTS ===

    if (sc.SetDefaults)
    {
        sc.GraphName = "Zone Reaction Analyzer [v3.2]";
        sc.StudyDescription =
            "Multi-TF zone reaction analyzer with unified CSV export";
        sc.AutoLoop = 1;
        sc.GraphRegion = 0;
        sc.FreeDLL = 0;
        sc.CalculationPrecedence = LOW_PREC_LEVEL;

        // --- Active chart count ---
        sc.Input[0].Name = "Active Chart Count";
        sc.Input[0].SetInt(9);
        sc.Input[0].SetIntLimits(1, 9);

        // --- 9 chart slots (3 inputs each: Number, StudyID, Label) ---
        for (int s = 0; s < MAX_CHART_SLOTS; s++)
        {
            int base = 1 + s * 3;
            SCString numName, idName, labelName;
            numName.Format("Chart %d Number (0=off)", s + 1);
            idName.Format("Chart %d V4 Study ID", s + 1);
            labelName.Format("Chart %d Label", s + 1);

            sc.Input[base].Name = numName;
            sc.Input[base].SetInt(CHART_DEFAULTS[s].chartNum);
            sc.Input[base].SetIntLimits(0, 500);

            sc.Input[base + 1].Name = idName;
            sc.Input[base + 1].SetInt(CHART_DEFAULTS[s].studyID);
            sc.Input[base + 1].SetIntLimits(1, 500);

            sc.Input[base + 2].Name = labelName;
            sc.Input[base + 2].SetPathAndFileName(CHART_DEFAULTS[s].label);
        }

        // --- Remaining inputs (28–33) ---
        sc.Input[28].Name = "Observation Window (Minutes)";
        sc.Input[28].SetInt(720);
        sc.Input[28].SetIntLimits(1, 1440);

        // Input[29] removed (was Zone Extension for interior touches)

        sc.Input[30].Name = "VP Ray Threshold (Ticks)";
        sc.Input[30].SetInt(0);
        sc.Input[30].SetIntLimits(0, 200);

        sc.Input[31].Name = "Enable CSV Export";
        sc.Input[31].SetYesNo(1);

        sc.Input[32].Name = "CSV Output Folder (blank=SC Data)";
        sc.Input[32].SetPathAndFileName("");

        sc.Input[33].Name = "Skip First N Bars (0=process all)";
        sc.Input[33].SetInt(0);
        sc.Input[33].SetIntLimits(0, 500000);

        // --- Subgraphs ---
        SG_DemandEdge.Name = "Demand Edge Touch";
        SG_DemandEdge.DrawStyle = DRAWSTYLE_ARROW_UP;
        SG_DemandEdge.PrimaryColor = RGB(0, 120, 255);
        SG_DemandEdge.LineWidth = 6;
        SG_DemandEdge.DrawZeros = false;

        SG_SupplyEdge.Name = "Supply Edge Touch";
        SG_SupplyEdge.DrawStyle = DRAWSTYLE_ARROW_DOWN;
        SG_SupplyEdge.PrimaryColor = RGB(200, 0, 0);
        SG_SupplyEdge.LineWidth = 6;
        SG_SupplyEdge.DrawZeros = false;

        SG_VPRayTouch.Name = "VP Ray Touch";
        SG_VPRayTouch.DrawStyle = DRAWSTYLE_DIAMOND;
        SG_VPRayTouch.PrimaryColor = RGB(255, 255, 0);
        SG_VPRayTouch.LineWidth = 5;
        SG_VPRayTouch.DrawZeros = false;

        SG_Reaction.Name = "Reaction Ticks";
        SG_Reaction.DrawStyle = DRAWSTYLE_IGNORE;
        SG_Reaction.DrawZeros = false;

        SG_Penetration.Name = "Penetration Ticks";
        SG_Penetration.DrawStyle = DRAWSTYLE_IGNORE;
        SG_Penetration.DrawZeros = false;

        return;
    }

    // === LAST CALL CLEANUP ===

    if (sc.LastCallToFunction)
    {
        TouchStorage* p = (TouchStorage*)sc.GetPersistentPointer(kTouchStoragePtr);
        if (p != nullptr)
        {
            sc.FreeMemory(p);
            sc.SetPersistentPointer(kTouchStoragePtr, nullptr);
        }
        return;
    }

    // === PERSISTENT STORAGE ===

    TouchStorage* pStorage = GetOrAllocateStorage(sc);
    if (pStorage == nullptr)
        return;

    int index = sc.Index;

    // === FULL RECALC RESET ===

    if (sc.UpdateStartIndex == 0 && index == 0)
    {
        pStorage->TouchCount = 0;
        pStorage->ZoneCount  = 0;
        memset(pStorage->Touches, 0, sizeof(pStorage->Touches));
        memset(pStorage->Zones, 0, sizeof(pStorage->Zones));
    }

    if (index < 1)
        return;

    // === READ INPUTS ===

    int   activeCount  = sc.Input[0].GetInt();
    if (activeCount < 1) activeCount = 1;
    if (activeCount > MAX_CHART_SLOTS) activeCount = MAX_CHART_SLOTS;

    int   obsMinutes   = sc.Input[28].GetInt();
    float vpThreshold  = sc.Input[30].GetInt() * sc.TickSize;
    bool  enableCSV    = sc.Input[31].GetYesNo() != 0;
    int   skipBars     = sc.Input[33].GetInt();
    float tickSize     = sc.TickSize;

    // === SKIP EARLY BARS ===

    if (skipBars > 0 && index < skipBars)
        return;

    // === BUILD CHART SLOT TABLE AND FETCH V4 ARRAYS ===

    ChartSlotData slots[MAX_CHART_SLOTS];
    memset(slots, 0, sizeof(slots));

    for (int s = 0; s < activeCount; s++)
    {
        int base = 1 + s * 3;
        slots[s].ChartNumber = sc.Input[base].GetInt();
        slots[s].StudyID     = sc.Input[base + 1].GetInt();
        SCString label = sc.Input[base + 2].GetPathAndFileName();
        strncpy(slots[s].Label, label.GetChars(), 31);
        slots[s].Label[31] = '\0';
        FetchChartSlot(sc, slots[s], index);
    }

    // === CLEAR SUBGRAPHS ===

    SG_DemandEdge[index]     = 0;
    SG_SupplyEdge[index]     = 0;
    SG_VPRayTouch[index]     = 0;
    SG_Reaction[index]       = 0;
    SG_Penetration[index]    = 0;

    float low   = sc.Low[index];
    float high  = sc.High[index];
    float low1  = sc.Low[index - 1];
    float high1 = sc.High[index - 1];

    // === ZONE DISCOVERY AND TOUCH DETECTION (per chart slot) ===

    for (int s = 0; s < activeCount; s++)
    {
        if (!slots[s].Valid)
            continue;

        int chartNum = slots[s].ChartNumber;

        float dTop  = slots[s].DemandTop[slots[s].V4Idx];
        float dBot  = slots[s].DemandBot[slots[s].V4Idx];
        float sTop  = slots[s].SupplyTop[slots[s].V4Idx];
        float sBot  = slots[s].SupplyBot[slots[s].V4Idx];
        float vpRay = (slots[s].VPImbalance.GetArraySize() > 0)
                      ? slots[s].VPImbalance[slots[s].V4Idx] : 0.0f;

        float dTop1  = slots[s].DemandTop[slots[s].V4Idx1];
        float dBot1  = slots[s].DemandBot[slots[s].V4Idx1];
        float sTop1  = slots[s].SupplyTop[slots[s].V4Idx1];
        float sBot1  = slots[s].SupplyBot[slots[s].V4Idx1];
        float vpRay1 = (slots[s].VPImbalance.GetArraySize() > 0)
                       ? slots[s].VPImbalance[slots[s].V4Idx1] : 0.0f;

        // v3.2 CHANGE: VP Ray proximity filter — stale V4 subgraph values
        // filtered by 3x zone width threshold (2026-03-22)
        // vpNearZone computed per-touch below using zone-local context.

        // --- Zone discovery ---
        if (dTop > 0 && dBot > 0)
            FindOrCreateZone(pStorage, dTop, dBot, true, chartNum, index);
        if (sTop > 0 && sBot > 0)
            FindOrCreateZone(pStorage, sTop, sBot, false, chartNum, index);

        // --- DEMAND_EDGE ---
        if (dTop > 0 && dBot > 0)
        {
            bool zoneConsistent = (dTop1 > 0 && fabs(dTop - dTop1) < tickSize * 2);
            bool touchNow       = (low <= dTop);
            bool notTouchBefore = (dTop1 == 0) || (low1 > dTop1);

            if (zoneConsistent && touchNow && notTouchBefore)
            {
                if (!IsDebouncedDuplicate(pStorage, kDemandEdge, dTop,
                                          tickSize, index, chartNum))
                {
                    int zoneIdx = FindOrCreateZone(pStorage, dTop, dBot,
                                                   true, chartNum, index);
                    int touchSeq = 1, ageBars = 0;
                    if (zoneIdx >= 0)
                    {
                        pStorage->Zones[zoneIdx].TouchCount++;
                        touchSeq = pStorage->Zones[zoneIdx].TouchCount;
                        ageBars  = index - pStorage->Zones[zoneIdx].FirstSeenBar;
                    }
                    float velocity = CalcApproachVelocity(sc, index, tickSize);
                    float trend    = CalcTrendSlope(sc, index, tickSize);

                    // v3.2: demand touch — VP must be within 3x zone width of dTop
                    bool vpNearZone = (vpRay > 0.0f) &&
                        (fabs(vpRay - dTop) < fabs(dTop - dBot) * 3.0f);

                    int idx = AddTouch(pStorage, index, dTop, kDemandEdge, -1,
                                       dTop, dBot, vpNearZone,
                                       vpNearZone ? vpRay : 0.0f,
                                       touchSeq, ageBars, velocity, trend,
                                       chartNum, slots[s].StudyID,
                                       s, slots[s].Label);
                    if (idx >= 0)
                        SG_DemandEdge[index] = low - (5 * tickSize);
                }
            }
        }

        // --- SUPPLY_EDGE ---
        if (sTop > 0 && sBot > 0)
        {
            bool zoneConsistent = (sBot1 > 0 && fabs(sBot - sBot1) < tickSize * 2);
            bool touchNow       = (high >= sBot);
            bool notTouchBefore = (sBot1 == 0) || (high1 < sBot1);

            if (zoneConsistent && touchNow && notTouchBefore)
            {
                if (!IsDebouncedDuplicate(pStorage, kSupplyEdge, sBot,
                                          tickSize, index, chartNum))
                {
                    int zoneIdx = FindOrCreateZone(pStorage, sTop, sBot,
                                                   false, chartNum, index);
                    int touchSeq = 1, ageBars = 0;
                    if (zoneIdx >= 0)
                    {
                        pStorage->Zones[zoneIdx].TouchCount++;
                        touchSeq = pStorage->Zones[zoneIdx].TouchCount;
                        ageBars  = index - pStorage->Zones[zoneIdx].FirstSeenBar;
                    }
                    float velocity = CalcApproachVelocity(sc, index, tickSize);
                    float trend    = CalcTrendSlope(sc, index, tickSize);

                    // v3.2: supply touch — VP must be within 3x zone width of sBot
                    bool vpNearZone = (vpRay > 0.0f) &&
                        (fabs(vpRay - sBot) < fabs(sTop - sBot) * 3.0f);

                    int idx = AddTouch(pStorage, index, sBot, kSupplyEdge, +1,
                                       sTop, sBot, vpNearZone,
                                       vpNearZone ? vpRay : 0.0f,
                                       touchSeq, ageBars, velocity, trend,
                                       chartNum, slots[s].StudyID,
                                       s, slots[s].Label);
                    if (idx >= 0)
                        SG_SupplyEdge[index] = high + (5 * tickSize);
                }
            }
        }

        // --- VP_RAY ---
        if (vpRay > 0)
        {
            bool rayTouchNow  = (low <= vpRay + vpThreshold) &&
                                (high >= vpRay - vpThreshold);
            bool rayNotBefore = (vpRay1 == 0)
                                || (low1 > vpRay1 + vpThreshold)
                                || (high1 < vpRay1 - vpThreshold);

            if (rayTouchNow && rayNotBefore)
            {
                if (!IsDebouncedDuplicate(pStorage, kVPRay, vpRay,
                                          tickSize, index, chartNum))
                {
                    float prevMid = (high1 + low1) * 0.5f;
                    int approachDir = (prevMid > vpRay) ? -1 : +1;

                    float zTop = 0, zBot = 0;
                    bool vpIsDemand = false;
                    if (dTop > 0 && dBot > 0)
                    {
                        zTop = dTop; zBot = dBot;
                        vpIsDemand = true;
                    }
                    else if (sTop > 0 && sBot > 0)
                    {
                        zTop = sTop; zBot = sBot;
                    }

                    int touchSeq = 0, ageBars = 0;
                    if (zTop > 0 && zBot > 0)
                    {
                        int zoneIdx = FindOrCreateZone(pStorage, zTop, zBot,
                                                       vpIsDemand, chartNum, index);
                        if (zoneIdx >= 0)
                        {
                            pStorage->Zones[zoneIdx].TouchCount++;
                            touchSeq = pStorage->Zones[zoneIdx].TouchCount;
                            ageBars  = index - pStorage->Zones[zoneIdx].FirstSeenBar;
                        }
                    }
                    float velocity = CalcApproachVelocity(sc, index, tickSize);
                    float trend    = CalcTrendSlope(sc, index, tickSize);

                    int idx = AddTouch(pStorage, index, vpRay, kVPRay, approachDir,
                                       zTop, zBot, true, vpRay,
                                       touchSeq, ageBars, velocity, trend,
                                       chartNum, slots[s].StudyID,
                                       s, slots[s].Label);
                    if (idx >= 0)
                        SG_VPRayTouch[index] = vpRay;
                }
            }
        }
    } // end per-slot loop

    // === UPDATE ACTIVE (UNRESOLVED) TOUCHES ===

    double observationDays = obsMinutes / 1440.0;

    for (int i = 0; i < pStorage->TouchCount; i++)
    {
        TrackedTouch& t = pStorage->Touches[i];
        if (!t.Active || t.Resolved)
            continue;
        if (index <= t.TouchBarIndex)
            continue;

        // Compute reaction and penetration
        float reactionVal, penetrationVal;

        if (t.ApproachDir == -1) // from above → expect bounce UP
        {
            reactionVal    = (high - t.TouchPrice) / tickSize;
            penetrationVal = (t.TouchPrice - low) / tickSize;
        }
        else // from below → expect bounce DOWN
        {
            reactionVal    = (t.TouchPrice - low) / tickSize;
            penetrationVal = (high - t.TouchPrice) / tickSize;
        }

        if (reactionVal < 0) reactionVal = 0;
        if (penetrationVal < 0) penetrationVal = 0;

        if (reactionVal > t.Reaction)
        {
            t.Reaction = reactionVal;
            t.ReactionPeakBar = index;
        }
        if (penetrationVal > t.Penetration)
            t.Penetration = penetrationVal;

        // Track first bar crossing each threshold
        for (int th = 0; th < NUM_RXN_THRESHOLDS; th++)
        {
            if (t.RxnCrossBar[th] == -1 && reactionVal >= RXN_THRESHOLDS[th])
                t.RxnCrossBar[th] = index;
        }
        for (int th = 0; th < NUM_PEN_THRESHOLDS; th++)
        {
            if (t.PenCrossBar[th] == -1 && penetrationVal >= PEN_THRESHOLDS[th])
                t.PenCrossBar[th] = index;
        }

        // Check zone broken (from the SAME chart slot that generated this touch)
        int si = t.SourceSlotIdx;
        if (!t.ZoneBroken && si >= 0 && si < activeCount && slots[si].Valid)
        {
            int v4i = slots[si].V4Idx;
            bool hasBrokenArrays = (slots[si].DemandBroken.GetArraySize() > 0 &&
                                    slots[si].SupplyBroken.GetArraySize() > 0);

            if (hasBrokenArrays && v4i >= 0 && v4i < slots[si].V4Size)
            {
                bool brokeNow = false;
                if (t.Type == kDemandEdge)
                {
                    if (slots[si].DemandBroken[v4i] != 0)
                        brokeNow = true;
                    if (slots[si].DemandTop[v4i] == 0 &&
                        slots[si].DemandBot[v4i] == 0)
                        brokeNow = true;
                }
                else if (t.Type == kSupplyEdge)
                {
                    if (slots[si].SupplyBroken[v4i] != 0)
                        brokeNow = true;
                    if (slots[si].SupplyTop[v4i] == 0 &&
                        slots[si].SupplyBot[v4i] == 0)
                        brokeNow = true;
                }
                if (brokeNow && !t.ZoneBroken)
                {
                    t.ZoneBroken = true;
                    t.BreakBarIndex = index;
                }
            }
        }

        // Time-based resolution
        double elapsed = sc.BaseDateTimeIn[index].GetAsDouble() -
                         sc.BaseDateTimeIn[t.TouchBarIndex].GetAsDouble();
        if (elapsed >= observationDays)
        {
            t.Resolved = true;
            t.ResolutionBar = index;

            SG_Reaction[t.TouchBarIndex]    = t.Reaction;
            SG_Penetration[t.TouchBarIndex] = t.Penetration;
        }
    }

    // === ON LAST BAR: EXPORT AND SUMMARIZE ===

    if (index == sc.ArraySize - 1)
    {
        if (enableCSV)
        {
            SCString csvFolder = sc.Input[32].GetPathAndFileName();
            WriteCSV(sc, pStorage, csvFolder);
        }

        LogSummary(sc, pStorage);
    }
}

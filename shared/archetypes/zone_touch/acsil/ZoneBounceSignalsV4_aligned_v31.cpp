// @study: Zone Bounce Signals V4
// @version: 4
// @author: ATEAM
// @type: indicator
// @features: inter-study, cross-chart, sc.UseTool, GetPersistentPointer, autoloop
// @looping: autoloop
// @complexity: complex
// @inputs: chart slots, mode thresholds, trend config, cascade window, stop/target per mode
// @summary: Multi-TF zone bounce signal overlay with five-mode scoring (M1/M3/M4/M5/Skip),
//           cascade awareness, session classification, and per-mode stop/target rays.

#include "sierrachart.h"

SCDLLName("Zone Bounce Signals V4")

// === CONSTANTS ===

// V4 subgraph indices (must match SupplyDemandZonesV4.cpp)
constexpr int V4_SG_NEAREST_DEMAND_TOP = 8;
constexpr int V4_SG_NEAREST_DEMAND_BOT = 9;
constexpr int V4_SG_NEAREST_SUPPLY_TOP = 10;
constexpr int V4_SG_NEAREST_SUPPLY_BOT = 11;
constexpr int V4_SG_VP_IMBALANCE_PRICE = 14;
constexpr int V4_SG_DEMAND_BROKEN      = 6;
constexpr int V4_SG_SUPPLY_BROKEN      = 7;

// Persistent storage
constexpr uint32_t ZBV4_STORAGE_MAGIC  = 0x5A425634; // "ZBV4"
constexpr int      MAX_TRACKED_SIGNALS = 5000;
constexpr int      MAX_TRACKED_ZONES   = 10000;
constexpr int      MAX_CHART_SLOTS     = 9;
constexpr int      EVICT_FRACTION      = 2; // evict oldest 1/N when full

// Drawing line number ranges (non-overlapping with V4)
constexpr int LN_BASE_STOP   = 84000;
constexpr int LN_BASE_TARGET = 88000;
constexpr int LN_BASE_LABEL  = 92000;

// Detection
constexpr int DEBOUNCE_TICKS = 3;

// Edge scoring
constexpr int APPROACH_LOOKBACK    = 10;  // bars to measure approach velocity
constexpr int DEFAULT_CASCADE_WINDOW = 50;

// === ENUMS ===

enum EdgeTouchType
{
    kDemandEdge = 0,
    kSupplyEdge = 1
};

enum TrendContext
{
    kWithTrend    = 0,
    kCounterTrend = 1,
    kNeutral      = 2
};

enum ModeAssignment
{
    kMode1Full = 0,
    kMode1Half = 1,
    kMode3     = 2,
    kMode4     = 3,
    kSkip      = 4,
    kMode5     = 5
};

enum SessionClass
{
    kOpen     = 0,
    kMidDay   = 1,
    kAfternoon = 2,
    kOffHours  = 3
};

enum CascadeState
{
    kCascadePriorHeld  = 0,
    kCascadeNoPrior    = 1,
    kCascadePriorBroke = 2
};

enum PersistentStorage
{
    kStoragePtr = 0
};

// === DATA STRUCTURES ===

struct TrackedZone
{
    float Top;
    float Bot;
    int   FirstSeenBar;
    int   FirstSeenHtfBar; // HTF bar index when zone first appeared (birth bar)
    int   TouchCount;
    int   SlotIdx;       // which chart slot owns this zone
    bool  IsDemand;
};

struct SignalRecord
{
    float TouchPrice;
    float ZoneTop;
    float ZoneBot;
    float TrendSlope;
    float VPRayPrice;
    float ApproachVelocity; // 10-bar approach speed in ticks
    float ZoneWidthTicks;   // zone top-bot in ticks
    float PenetrationTicks; // depth into zone on touch bar
    int   BarIndex;
    int   TouchSequence;
    int   Type;          // EdgeTouchType
    int   TrendCtx;      // TrendContext
    int   ModeAssignment; // ModeAssignment enum
    int   QualityScore;   // 0-100
    int   ContextScore;   // 0-80
    int   TotalScore;     // quality + context
    int   TFConfluence;  // how many TF charts have a zone at this price
    int   ZoneAgeBars;   // bars since zone first appeared
    int   TFWeightScore; // source TF quality weight 0-25
    int   SessionClass;  // SessionClass enum
    int   DayOfWeek;     // SUNDAY..SATURDAY
    int   CascadeState;  // CascadeState enum
    int   SourceSlot;
    int   SourceHtfBar;    // HTF bar index at detection time
    int   ConfirmedBar;    // base bar where HTF bar closed (arrow/label placed here)
    float DbgPrevHigh;     // prevBar price (for notTouchBefore debug)
    float DbgPrevSBot;     // zone edge at prevBar's HTF bar
    float DbgEvalHigh;     // evalBar price (for touchNow debug)
    float DbgEvalSBot;     // zone edge at evalBar's HTF bar
    bool  HasVPRay;
    bool  CascadeActive;   // shorthand: prior broke
    bool  HtfConfirmed;    // true once the source HTF bar has closed
    bool  DrawingsPlaced;
    bool  RaysResolved;    // true once price hit stop or target (rays deleted)
    bool  Active;
};

struct SignalStorage
{
    uint32_t     MagicNumber;
    int          SignalCount;
    int          ZoneCount;
    int          LastBreakBar;   // cascade: most recent bar where any zone broke
    int          LastHeldBar;    // cascade: most recent bar where a signal was created
    SignalRecord Signals[MAX_TRACKED_SIGNALS];
    TrackedZone  Zones[MAX_TRACKED_ZONES];
};

// Per-bar scratch data for one chart slot (not persisted)
struct ChartSlotData
{
    int ChartNumber;
    int StudyID;
    SCFloatArray DemandTop;
    SCFloatArray DemandBot;
    SCFloatArray SupplyTop;
    SCFloatArray SupplyBot;
    SCFloatArray VPImbalance;
    SCFloatArray DemandBroken;   // V4 subgraph[6]
    SCFloatArray SupplyBroken;   // V4 subgraph[7]
    int  V4Size;
    int  V4Idx;       // mapped bar index for current bar
    int  V4Idx1;      // mapped bar index for previous bar (index-1)
    int  V4Idx2;      // mapped bar index for two bars ago (index-2)
    int  TFWeightScore; // 0-25 based on chart bar period
    bool Valid;       // true if arrays fetched and indices in range
};

// === HELPERS ===

static const char* TrendLabel(int ctx)
{
    switch (ctx) {
        case kWithTrend:    return "WT";
        case kCounterTrend: return "CT";
        case kNeutral:      return "NT";
        default:            return "??";
    }
}

// === HELPER: Allocate or validate persistent storage ===

static SignalStorage* GetOrAllocateStorage(SCStudyInterfaceRef sc)
{
    SignalStorage* p = (SignalStorage*)sc.GetPersistentPointer(kStoragePtr);

    if (p == nullptr || p->MagicNumber != ZBV4_STORAGE_MAGIC)
    {
        if (p != nullptr)
            sc.FreeMemory(p);

        p = (SignalStorage*)sc.AllocateMemory(sizeof(SignalStorage));
        if (p == nullptr)
            return nullptr;

        memset(p, 0, sizeof(SignalStorage));
        p->MagicNumber = ZBV4_STORAGE_MAGIC;
        sc.SetPersistentPointer(kStoragePtr, p);
    }

    return p;
}

// === HELPER: Evict oldest signals when full ===
// Deletes drawings for evicted signals, shifts remaining signals down.

static void EvictOldSignals(SCStudyInterfaceRef sc, SignalStorage* p)
{
    int evictCount = p->SignalCount / EVICT_FRACTION;
    if (evictCount < 1) evictCount = 1;

    // Delete drawings for evicted signals
    for (int i = 0; i < evictCount; i++)
    {
        sc.DeleteACSChartDrawing(sc.ChartNumber, TOOL_DELETE_CHARTDRAWING, LN_BASE_STOP   + i);
        sc.DeleteACSChartDrawing(sc.ChartNumber, TOOL_DELETE_CHARTDRAWING, LN_BASE_TARGET + i);
        sc.DeleteACSChartDrawing(sc.ChartNumber, TOOL_DELETE_CHARTDRAWING, LN_BASE_LABEL  + i);
    }

    // Shift remaining signals down
    int remaining = p->SignalCount - evictCount;
    memmove(&p->Signals[0], &p->Signals[evictCount], remaining * sizeof(SignalRecord));

    // Mark shifted signals for redraw (line numbers changed)
    for (int i = 0; i < remaining; i++)
        p->Signals[i].DrawingsPlaced = false;

    // Clear freed slots
    memset(&p->Signals[remaining], 0, evictCount * sizeof(SignalRecord));
    p->SignalCount = remaining;
}

// === HELPER: Evict oldest zones when full ===

static void EvictOldZones(SignalStorage* p)
{
    int evictCount = p->ZoneCount / EVICT_FRACTION;
    if (evictCount < 1) evictCount = 1;

    int remaining = p->ZoneCount - evictCount;
    memmove(&p->Zones[0], &p->Zones[evictCount], remaining * sizeof(TrackedZone));
    memset(&p->Zones[remaining], 0, evictCount * sizeof(TrackedZone));
    p->ZoneCount = remaining;
}

// === HELPER: Find or create a tracked zone ===
// Zones are keyed by (top, bot, isDemand, slotIdx) to track per-TF identity.

static int FindOrCreateZone(SignalStorage* p, float top, float bot,
                            bool isDemand, int slotIdx, int barIndex,
                            int htfBarIdx, float tolerance = 0.01f)
{
    for (int i = 0; i < p->ZoneCount; i++)
    {
        if (p->Zones[i].IsDemand == isDemand &&
            p->Zones[i].SlotIdx == slotIdx &&
            fabs(p->Zones[i].Top - top) < tolerance &&
            fabs(p->Zones[i].Bot - bot) < tolerance)
            return i;
    }

    // Evict oldest half if full
    if (p->ZoneCount >= MAX_TRACKED_ZONES)
        EvictOldZones(p);

    int idx = p->ZoneCount;
    p->Zones[idx].Top             = top;
    p->Zones[idx].Bot             = bot;
    p->Zones[idx].FirstSeenBar    = barIndex;
    p->Zones[idx].FirstSeenHtfBar = htfBarIdx;
    p->Zones[idx].TouchCount      = 0;
    p->Zones[idx].SlotIdx         = slotIdx;
    p->Zones[idx].IsDemand        = isDemand;
    p->ZoneCount++;
    return idx;
}

// === HELPER: Debounce duplicate touches ===
// Only suppress duplicate signals within the last DEBOUNCE_BAR_WINDOW bars.
// Without this limit, the debounce would accumulate across the entire chart
// history and suppress legitimate re-touches of the same zone weeks later.

constexpr int DEBOUNCE_BAR_WINDOW = 20;

static bool IsDebouncedDuplicate(SignalStorage* p, int type, float price,
                                  float tickSize, int currentBar, int sourceSlot)
{
    float threshold = DEBOUNCE_TICKS * tickSize;
    for (int i = p->SignalCount - 1; i >= 0; i--)
    {
        SignalRecord& s = p->Signals[i];
        if (!s.Active)
            continue;
        // Only check recent signals -- allow re-touches after the window
        if (currentBar - s.BarIndex > DEBOUNCE_BAR_WINDOW)
            break; // signals are ordered by bar, so earlier ones are even older
        if (s.SourceSlot == sourceSlot &&
            s.Type == type && fabs(s.TouchPrice - price) < threshold)
            return true;
    }
    return false;
}

// === HELPER: Trend slope calculation ===

static float CalcTrendSlope(SCStudyInterfaceRef sc, int barIndex, float tickSize, int lookback)
{
    if (barIndex < lookback)
        return 0.0f;
    float priceNow  = sc.BaseData[SC_LAST][barIndex];
    float pricePrev = sc.BaseData[SC_LAST][barIndex - lookback];
    return (priceNow - pricePrev) / tickSize;
}

// === HELPER: 10-bar approach velocity (absolute, in ticks) ===

static float CalcApproachVelocity(SCStudyInterfaceRef sc, int barIndex, float tickSize)
{
    if (barIndex < APPROACH_LOOKBACK)
        return 0.0f;
    float priceNow  = sc.BaseData[SC_LAST][barIndex];
    float pricePrev = sc.BaseData[SC_LAST][barIndex - APPROACH_LOOKBACK];
    return fabs(priceNow - pricePrev) / tickSize;
}

// === HELPER: Classify trend context ===

static int ClassifyTrend(int touchType, float trendSlope, float threshold)
{
    if (touchType == kDemandEdge)
    {
        if (trendSlope > threshold)  return kWithTrend;
        if (trendSlope < -threshold) return kCounterTrend;
        return kNeutral;
    }
    else // kSupplyEdge
    {
        if (trendSlope < -threshold) return kWithTrend;
        if (trendSlope > threshold)  return kCounterTrend;
        return kNeutral;
    }
}

// === HELPER: Count TF confluence ===
// For a touch at a given price+type, count how many other active chart slots
// also have a zone boundary within tolerance at the current bar.

static int CountTFConfluence(ChartSlotData slots[], int activeCount,
                             int touchType, float touchPrice, float tolerance,
                             int excludeSlot)
{
    int count = 1; // count the slot that detected the touch
    for (int s = 0; s < activeCount; s++)
    {
        if (s == excludeSlot || !slots[s].Valid || slots[s].ChartNumber == 0)
            continue;

        float edgePrice = 0.0f;
        if (touchType == kDemandEdge)
            edgePrice = slots[s].DemandTop[slots[s].V4Idx];
        else
            edgePrice = slots[s].SupplyBot[slots[s].V4Idx];

        if (edgePrice > 0 && fabs(edgePrice - touchPrice) <= tolerance)
            count++;
    }
    return count;
}

// === HELPER: Check bar-level dedup across chart slots ===
// Returns true if a signal was already recorded at this bar+type within tolerance.

static bool IsBarDuplicate(SignalStorage* p, int barIndex, int touchType,
                           float touchPrice, float tolerance)
{
    for (int i = p->SignalCount - 1; i >= 0; i--)
    {
        SignalRecord& s = p->Signals[i];
        if (s.BarIndex != barIndex)
            break; // signals are ordered by bar; earlier bars won't match
        if (s.Type == touchType && fabs(s.TouchPrice - touchPrice) <= tolerance)
            return true;
    }
    return false;
}

// === SCORING FUNCTIONS ===

// Compute timeframe weight score based on chart bar period (seconds)
static int CalcTFWeightScore(SCStudyInterfaceRef sc, int chartNumber)
{
    n_ACSIL::s_BarPeriod bp;
    sc.GetBarPeriodParametersForChart(chartNumber, bp);
    if (bp.ChartDataType != INTRADAY_DATA || bp.IntradayChartBarPeriodType != IBPT_DAYS_MINS_SECS)
        return 0;
    int seconds = bp.IntradayChartBarPeriodParameter1;
    if (seconds >= 14400) return 25;  // 240m+
    if (seconds >= 7200)  return 18;  // 120m
    if (seconds >= 5400)  return 15;  // 90m
    if (seconds >= 3600)  return 12;  // 60m
    if (seconds >= 1800)  return 8;   // 30m
    if (seconds >= 900)   return 5;   // 15m
    return 0;
}

// Compute zone quality score (0-65) — v3 model: TF + Width + VP Ray
static int CalcZoneQualityScore(int tfWeight, float zoneWidthTicks, bool hasVPRay)
{
    int score = tfWeight;
    // Zone width: 0-20
    if (zoneWidthTicks >= 401.0f)      score += 20;
    else if (zoneWidthTicks >= 161.0f) score += 15;
    else if (zoneWidthTicks >= 81.0f)  score += 8;
    // VP ray: 0-20
    if (hasVPRay) score += 20;
    return score;
}

// Classify the session based on time of day (ET/CT assumed)
static int ClassifySession(int hour, int minute)
{
    int hhmm = hour * 100 + minute;
    if (hhmm >= 830 && hhmm < 1000)  return kOpen;
    if (hhmm >= 1000 && hhmm < 1400) return kMidDay;
    if (hhmm >= 1400 && hhmm < 1700) return kAfternoon;
    return kOffHours;
}

// Determine cascade state based on recent breaks/holds
static int DetermineCascadeState(int evalBar, int lastBreakBar, int lastHeldBar, int cascadeWindow)
{
    bool recentBreak = (lastBreakBar > 0 && (evalBar - lastBreakBar) <= cascadeWindow);
    bool recentHeld  = (lastHeldBar > 0 && (evalBar - lastHeldBar) <= cascadeWindow);
    if (recentBreak) return kCascadePriorBroke;
    if (recentHeld)  return kCascadePriorHeld;
    return kCascadeNoPrior;
}

// Compute context score (0-70) — v3 model: Cascade + Session + Velocity + Penetration
// Note: backtest model includes RxnSpeed (+20) which is post-hoc and not available at signal time
static int CalcContextScore(int cascadeState, int sessionCls,
                             float approachVel, float penetrationTicks)
{
    int score = 0;
    // Cascade: 0-30
    if (cascadeState == kCascadePriorHeld)   score += 30;
    else if (cascadeState == kCascadeNoPrior) score += 20;
    // Session: 0-15
    if (sessionCls == kOpen)           score += 15;
    else if (sessionCls == kMidDay)    score += 12;
    else if (sessionCls == kAfternoon) score += 5;
    // Approach velocity: 0-10
    if (approachVel >= 101.0f)      score += 10;
    else if (approachVel >= 51.0f)  score += 8;
    else if (approachVel >= 21.0f)  score += 5;
    else                            score += 3;
    // Penetration: 0-15
    if (penetrationTicks < 30.0f)        score += 15;
    else if (penetrationTicks <= 80.0f)  score += 10;
    else if (penetrationTicks <= 120.0f) score += 5;
    return score;
}

// Compute penetration depth into zone on touch bar (in ticks)
static float CalcPenetrationTicks(int touchType, float touchEdge,
                                   float barLow, float barHigh, float tickSize)
{
    float pen;
    if (touchType == kDemandEdge)
        pen = (touchEdge - barLow) / tickSize;
    else
        pen = (barHigh - touchEdge) / tickSize;
    return pen > 0.0f ? pen : 0.0f;
}

// === LABEL HELPERS ===

static const char* ModeLabel(int mode)
{
    switch (mode) {
        case kMode1Full: return "M1F";
        case kMode1Half: return "M1H";
        case kMode3:     return "M3";
        case kMode4:     return "M4";
        case kMode5:     return "M5";
        default:         return "---";
    }
}

static void BuildEdgeLabel(SCString& out, int mode, int touchType, int seq,
                           int trendCtx, int tfCount, bool hasVP, int totalScore,
                           bool gradeOnly)
{
    char typeChar = (touchType == kDemandEdge) ? 'D' : 'S';
    const char* modeStr = ModeLabel(mode);
    if (gradeOnly)
    {
        out.Format("%s [%d]", modeStr, totalScore);
        return;
    }
    const char* trendStr = TrendLabel(trendCtx);
    const char* vpStr = hasVP ? " +VP" : "";
    out.Format("%s %c%d %s %dTF [%d]%s", modeStr, typeChar, seq, trendStr, tfCount, totalScore, vpStr);
}

// === HELPER: Delete all signal drawings ===

static void DeleteAllSignalDrawings(SCStudyInterfaceRef sc, int maxSlots)
{
    for (int i = 0; i < maxSlots; i++)
    {
        sc.DeleteACSChartDrawing(sc.ChartNumber, TOOL_DELETE_CHARTDRAWING, LN_BASE_STOP   + i);
        sc.DeleteACSChartDrawing(sc.ChartNumber, TOOL_DELETE_CHARTDRAWING, LN_BASE_TARGET + i);
        sc.DeleteACSChartDrawing(sc.ChartNumber, TOOL_DELETE_CHARTDRAWING, LN_BASE_LABEL  + i);
    }
}

// === HELPER: Mode-specific stop/target calculation ===

static void GetModeStopTarget(int mode, float zoneWidthTicks,
                               int m3Stop, int m3Target,
                               int m4Stop, int m4Target,
                               int m5Stop, int m5Target,
                               int& outStop, int& outTarget)
{
    switch (mode)
    {
        case kMode1Full:
        case kMode1Half:
        {
            int scaled = (int)(zoneWidthTicks * 0.35f);
            if (scaled < 80)  scaled = 80;
            if (scaled > 200) scaled = 200;
            outStop = scaled;
            outTarget = scaled * 2;
            break;
        }
        case kMode3:
            outStop = m3Stop;
            outTarget = m3Target;
            break;
        case kMode4:
            outStop = m4Stop;
            outTarget = m4Target;
            break;
        case kMode5:
            outStop = m5Stop;
            outTarget = m5Target;
            break;
        default:
            outStop = 0;
            outTarget = 0;
            break;
    }
}

// === HELPER: Place drawings for a single signal ===

static void PlaceSignalDrawings(SCStudyInterfaceRef sc, SignalRecord& sig,
                                int slotIdx, float tickSize,
                                int mode, int totalScore,
                                int m3Stop, int m3Target,
                                int m4Stop, int m4Target,
                                int m5Stop, int m5Target,
                                bool showLines, bool showLabels,
                                bool gradeOnly)
{
    bool isDemand = (sig.Type == kDemandEdge);
    int drawBar = sig.BarIndex;

    // --- Label ---
    if (showLabels)
    {
        SCString labelText;
        BuildEdgeLabel(labelText, mode, sig.Type, sig.TouchSequence,
                       sig.TrendCtx, sig.TFConfluence, sig.HasVPRay,
                       totalScore, gradeOnly);

        // Mode-specific label colors
        COLORREF labelColor;
        switch (mode)
        {
            case kMode1Full:
            case kMode1Half:
                labelColor = isDemand ? RGB(0, 120, 255) : RGB(200, 0, 0);
                break;
            case kMode3:
                labelColor = isDemand ? RGB(255, 140, 0) : RGB(200, 0, 200);
                break;
            case kMode4:
                labelColor = isDemand ? RGB(0, 200, 200) : RGB(255, 100, 150);
                break;
            case kMode5:
                labelColor = isDemand ? RGB(0, 180, 80) : RGB(180, 200, 0);
                break;
            default: // kSkip
                labelColor = RGB(128, 128, 128);
                break;
        }

        s_UseTool LabelTool;
        LabelTool.Clear();
        LabelTool.ChartNumber = sc.ChartNumber;
        LabelTool.DrawingType = DRAWING_TEXT;
        LabelTool.AddMethod   = UTAM_ADD_OR_ADJUST;
        LabelTool.LineNumber  = LN_BASE_LABEL + slotIdx;
        LabelTool.Region      = 0;
        float barLow  = sc.Low[drawBar];
        float barHigh = sc.High[drawBar];
        LabelTool.BeginIndex  = drawBar;
        LabelTool.BeginValue  = isDemand
                                ? barLow - (50 * tickSize)
                                : barHigh + (50 * tickSize);
        LabelTool.Text        = labelText;
        LabelTool.Color       = labelColor;
        LabelTool.FontSize    = 8;
        LabelTool.FontBold    = (mode == kMode1Full || mode == kMode1Half) ? 1 : 0;
        LabelTool.TextAlignment = DT_CENTER | (isDemand ? DT_TOP : DT_BOTTOM);
        LabelTool.TransparentLabelBackground = 1;
        LabelTool.AddAsUserDrawnDrawing = 0;
        sc.UseTool(LabelTool);
    }

    // --- Stop and Target rays (non-Skip modes only) ---
    if (showLines && mode != kSkip)
    {
        int sigStop, sigTarget;
        GetModeStopTarget(mode, sig.ZoneWidthTicks,
                          m3Stop, m3Target, m4Stop, m4Target,
                          m5Stop, m5Target,
                          sigStop, sigTarget);

        if (sigStop > 0)
        {
            float stopOffset   = sigStop * tickSize;
            float targetOffset = sigTarget * tickSize;

            float stopPrice, targetPrice;
            if (isDemand)
            {
                stopPrice   = sig.TouchPrice - stopOffset;
                targetPrice = sig.TouchPrice + targetOffset;
            }
            else
            {
                stopPrice   = sig.TouchPrice + stopOffset;
                targetPrice = sig.TouchPrice - targetOffset;
            }

            s_UseTool RayTool;
            RayTool.Clear();
            RayTool.ChartNumber = sc.ChartNumber;
            RayTool.DrawingType = DRAWING_HORIZONTAL_RAY;
            RayTool.AddMethod   = UTAM_ADD_OR_ADJUST;
            RayTool.Region      = 0;
            RayTool.AddAsUserDrawnDrawing      = 0;
            RayTool.LineStyle                  = LINESTYLE_DASH;
            RayTool.LineWidth                  = 1;
            RayTool.DisplayHorizontalLineValue = 1;

            // Stop ray (red)
            RayTool.LineNumber = LN_BASE_STOP + slotIdx;
            RayTool.BeginIndex = drawBar;
            RayTool.BeginValue = stopPrice;
            RayTool.Color      = RGB(200, 0, 0);
            sc.UseTool(RayTool);

            // Target ray (blue)
            RayTool.LineNumber = LN_BASE_TARGET + slotIdx;
            RayTool.BeginValue = targetPrice;
            RayTool.Color      = RGB(0, 120, 255);
            sc.UseTool(RayTool);
        }
    }

    sig.DrawingsPlaced = true;
}

// === HELPER: Play mode-specific alert sound on live bar ===

static void PlayModeAlert(SCStudyInterfaceRef sc, int mode, int touchType,
                           int seq, int totalScore,
                           unsigned int m1Sound, unsigned int m3Sound,
                           unsigned int m4Sound, unsigned int m5Sound)
{
    unsigned int soundNum = 0;
    switch (mode)
    {
        case kMode1Full:
        case kMode1Half: soundNum = m1Sound; break;
        case kMode3:     soundNum = m3Sound; break;
        case kMode4:     soundNum = m4Sound; break;
        case kMode5:     soundNum = m5Sound; break;
        default: return;
    }
    if (soundNum < 2) return;  // 0=Disabled, 1=No Sound

    const char* modeStr = ModeLabel(mode);
    const char* sideStr = (touchType == kDemandEdge) ? "Demand" : "Supply";
    SCString msg;
    msg.Format("%s %s S%d [%d]", modeStr, sideStr, seq, totalScore);
    sc.PlaySound(soundNum, msg, 0);
}

// === HELPER: Fetch V4 arrays for a chart slot ===

static void FetchChartSlot(SCStudyInterfaceRef sc, ChartSlotData& slot, int index)
{
    slot.Valid = false;
    slot.TFWeightScore = 0;

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
    slot.V4Idx2 = (index >= 2)
                  ? sc.GetNearestMatchForDateTimeIndex(slot.ChartNumber, index - 2)
                  : -1;

    if (slot.V4Idx < 0 || slot.V4Idx >= slot.V4Size ||
        slot.V4Idx1 < 0 || slot.V4Idx1 >= slot.V4Size)
        return;
    if (slot.V4Idx2 < 0 || slot.V4Idx2 >= slot.V4Size)
        slot.V4Idx2 = slot.V4Idx1;  // safe fallback (won't pass zoneConsistent)

    slot.Valid = true;
    slot.TFWeightScore = CalcTFWeightScore(sc, slot.ChartNumber);
}


// === MAIN STUDY FUNCTION ===

SCSFExport scsf_ZoneBounceSignalsV4(SCStudyInterfaceRef sc)
{
    // --- Input references ---
    SCInputRef InputActiveCount       = sc.Input[0];
    SCInputRef InputChart1Num         = sc.Input[1];
    SCInputRef InputChart1Study       = sc.Input[2];
    SCInputRef InputChart2Num         = sc.Input[3];
    SCInputRef InputChart2Study       = sc.Input[4];
    SCInputRef InputChart3Num         = sc.Input[5];
    SCInputRef InputChart3Study       = sc.Input[6];
    SCInputRef InputChart4Num         = sc.Input[7];
    SCInputRef InputChart4Study       = sc.Input[8];
    SCInputRef InputChart5Num         = sc.Input[9];
    SCInputRef InputChart5Study       = sc.Input[10];
    SCInputRef InputChart6Num         = sc.Input[11];
    SCInputRef InputChart6Study       = sc.Input[12];
    SCInputRef InputChart7Num         = sc.Input[13];
    SCInputRef InputChart7Study       = sc.Input[14];
    SCInputRef InputChart8Num         = sc.Input[15];
    SCInputRef InputChart8Study       = sc.Input[16];
    SCInputRef InputChart9Num         = sc.Input[17];
    SCInputRef InputChart9Study       = sc.Input[18];
    // Scoring
    SCInputRef InputM1FullThreshold   = sc.Input[19];
    SCInputRef InputM1HalfThreshold   = sc.Input[20];
    SCInputRef InputMaxTouchSeq       = sc.Input[21];
    SCInputRef InputCascadeWindow     = sc.Input[22];
    SCInputRef InputConfluenceTol     = sc.Input[23];
    // Trend
    SCInputRef InputTrendMethod       = sc.Input[24];
    SCInputRef InputTrendThreshold    = sc.Input[25];
    SCInputRef InputSlopeLookback     = sc.Input[26];
    SCInputRef InputFastEMAPeriod     = sc.Input[27];
    SCInputRef InputSlowEMAPeriod     = sc.Input[28];
    // Stop/Target
    SCInputRef InputM3StopTicks       = sc.Input[29];
    SCInputRef InputM3TargetTicks     = sc.Input[30];
    SCInputRef InputM4StopTicks       = sc.Input[31];
    SCInputRef InputM4TargetTicks     = sc.Input[32];
    SCInputRef InputM5StopTicks       = sc.Input[33];
    SCInputRef InputM5TargetTicks     = sc.Input[34];
    // Display
    SCInputRef InputShowLines         = sc.Input[35];
    SCInputRef InputShowSkipped       = sc.Input[36];
    SCInputRef InputMaxVisibleRays    = sc.Input[37];
    SCInputRef InputLabelDetail       = sc.Input[38];
    SCInputRef InputSkipBars          = sc.Input[39];
    // Alerts
    SCInputRef InputEnableAlerts      = sc.Input[40];
    SCInputRef InputM1AlertSound      = sc.Input[41];
    SCInputRef InputM3AlertSound      = sc.Input[42];
    SCInputRef InputM4AlertSound      = sc.Input[43];
    SCInputRef InputM5AlertSound      = sc.Input[44];
    SCInputRef InputCSVPath           = sc.Input[46];
    SCInputRef InputExportCSV         = sc.Input[47];
    SCInputRef InputSuppressLabels    = sc.Input[48];

    // --- Subgraph references ---
    SCSubgraphRef SG_M1Demand   = sc.Subgraph[0];   // M1F (Full) — kept at [0] for backward compat
    SCSubgraphRef SG_M1Supply   = sc.Subgraph[1];   // M1F (Full)
    SCSubgraphRef SG_M3Demand   = sc.Subgraph[2];
    SCSubgraphRef SG_M3Supply   = sc.Subgraph[3];
    SCSubgraphRef SG_M4Demand   = sc.Subgraph[4];
    SCSubgraphRef SG_M4Supply   = sc.Subgraph[5];
    SCSubgraphRef SG_SkipDemand = sc.Subgraph[6];
    SCSubgraphRef SG_SkipSupply = sc.Subgraph[7];
    SCSubgraphRef SG_M5Demand   = sc.Subgraph[8];
    SCSubgraphRef SG_M5Supply   = sc.Subgraph[9];
    SCSubgraphRef SG_TrendSlope = sc.Subgraph[10];
    SCSubgraphRef SG_TrendZero  = sc.Subgraph[11];
    SCSubgraphRef SG_M1HDemand  = sc.Subgraph[13];  // M1H (Half) — separate from M1F
    SCSubgraphRef SG_M1HSupply  = sc.Subgraph[14];  // M1H (Half)

    // === SET DEFAULTS ===

    if (sc.SetDefaults)
    {
        sc.GraphName = "Zone Bounce Signals V4";
        sc.StudyDescription = "Multi-TF zone bounce signal overlay with five-mode scoring (M1/M3/M4/M5) and cascade awareness";
        sc.AutoLoop = 1;
        sc.GraphRegion = 0;
        sc.FreeDLL = 0;
        sc.CalculationPrecedence = LOW_PREC_LEVEL;

        // --- Chart slot inputs (0-18) ---
        InputActiveCount.Name = "Active Chart Count";
        InputActiveCount.SetInt(9);
        InputActiveCount.SetIntLimits(1, 9);

        InputChart1Num.Name   = "Chart 1 Number (0=off)";
        InputChart1Num.SetInt(3);
        InputChart1Num.SetIntLimits(0, 500);
        InputChart1Study.Name = "Chart 1 V4 Study ID";
        InputChart1Study.SetInt(1);
        InputChart1Study.SetIntLimits(1, 500);

        InputChart2Num.Name   = "Chart 2 Number (0=off)";
        InputChart2Num.SetInt(4);
        InputChart2Num.SetIntLimits(0, 500);
        InputChart2Study.Name = "Chart 2 V4 Study ID";
        InputChart2Study.SetInt(3);
        InputChart2Study.SetIntLimits(1, 500);

        InputChart3Num.Name   = "Chart 3 Number (0=off)";
        InputChart3Num.SetInt(5);
        InputChart3Num.SetIntLimits(0, 500);
        InputChart3Study.Name = "Chart 3 V4 Study ID";
        InputChart3Study.SetInt(2);
        InputChart3Study.SetIntLimits(1, 500);

        InputChart4Num.Name   = "Chart 4 Number (0=off)";
        InputChart4Num.SetInt(6);
        InputChart4Num.SetIntLimits(0, 500);
        InputChart4Study.Name = "Chart 4 V4 Study ID";
        InputChart4Study.SetInt(3);
        InputChart4Study.SetIntLimits(1, 500);

        InputChart5Num.Name   = "Chart 5 Number (0=off)";
        InputChart5Num.SetInt(7);
        InputChart5Num.SetIntLimits(0, 500);
        InputChart5Study.Name = "Chart 5 V4 Study ID";
        InputChart5Study.SetInt(1);
        InputChart5Study.SetIntLimits(1, 500);

        InputChart6Num.Name   = "Chart 6 Number (0=off)";
        InputChart6Num.SetInt(2);
        InputChart6Num.SetIntLimits(0, 500);
        InputChart6Study.Name = "Chart 6 V4 Study ID";
        InputChart6Study.SetInt(4);
        InputChart6Study.SetIntLimits(1, 500);

        InputChart7Num.Name   = "Chart 7 Number (0=off)";
        InputChart7Num.SetInt(8);
        InputChart7Num.SetIntLimits(0, 500);
        InputChart7Study.Name = "Chart 7 V4 Study ID";
        InputChart7Study.SetInt(3);
        InputChart7Study.SetIntLimits(1, 500);

        InputChart8Num.Name   = "Chart 8 Number (0=off)";
        InputChart8Num.SetInt(14);
        InputChart8Num.SetIntLimits(0, 500);
        InputChart8Study.Name = "Chart 8 V4 Study ID";
        InputChart8Study.SetInt(2);
        InputChart8Study.SetIntLimits(1, 500);

        InputChart9Num.Name   = "Chart 9 Number (0=off)";
        InputChart9Num.SetInt(9);
        InputChart9Num.SetIntLimits(0, 500);
        InputChart9Study.Name = "Chart 9 V4 Study ID";
        InputChart9Study.SetInt(2);
        InputChart9Study.SetIntLimits(1, 500);

        // --- Scoring inputs (19-23) ---
        InputM1FullThreshold.Name = "M1 Full Score Threshold";
        InputM1FullThreshold.SetInt(90);
        InputM1FullThreshold.SetIntLimits(0, 155);

        InputM1HalfThreshold.Name = "M1 Half Score Threshold";
        InputM1HalfThreshold.SetInt(60);
        InputM1HalfThreshold.SetIntLimits(0, 155);

        InputMaxTouchSeq.Name = "Max Touch Sequence";
        InputMaxTouchSeq.SetInt(2);
        InputMaxTouchSeq.SetIntLimits(1, 10);

        InputCascadeWindow.Name = "Cascade Window (Bars)";
        InputCascadeWindow.SetInt(DEFAULT_CASCADE_WINDOW);
        InputCascadeWindow.SetIntLimits(1, 500);

        InputConfluenceTol.Name = "TF Confluence Tolerance (Ticks)";
        InputConfluenceTol.SetInt(2);
        InputConfluenceTol.SetIntLimits(0, 50);

        // --- Trend inputs (24-28) ---
        InputTrendMethod.Name = "Trend Method";
        InputTrendMethod.SetCustomInputStrings("50-bar Slope;EMA Crossover");
        InputTrendMethod.SetCustomInputIndex(0);

        InputTrendThreshold.Name = "Trend Threshold (Ticks)";
        InputTrendThreshold.SetInt(10);
        InputTrendThreshold.SetIntLimits(0, 500);

        InputSlopeLookback.Name = "Slope Lookback (Bars)";
        InputSlopeLookback.SetInt(50);
        InputSlopeLookback.SetIntLimits(5, 500);

        InputFastEMAPeriod.Name = "Fast EMA Period";
        InputFastEMAPeriod.SetInt(20);
        InputFastEMAPeriod.SetIntLimits(2, 200);

        InputSlowEMAPeriod.Name = "Slow EMA Period";
        InputSlowEMAPeriod.SetInt(50);
        InputSlowEMAPeriod.SetIntLimits(2, 500);

        // --- Stop/Target inputs (29-34) ---
        InputM3StopTicks.Name = "M3 Stop Ticks";
        InputM3StopTicks.SetInt(30);
        InputM3StopTicks.SetIntLimits(1, 500);

        InputM3TargetTicks.Name = "M3 Target Ticks";
        InputM3TargetTicks.SetInt(240);
        InputM3TargetTicks.SetIntLimits(1, 2000);

        InputM4StopTicks.Name = "M4 Stop Ticks";
        InputM4StopTicks.SetInt(80);
        InputM4StopTicks.SetIntLimits(1, 500);

        InputM4TargetTicks.Name = "M4 Target Ticks";
        InputM4TargetTicks.SetInt(40);
        InputM4TargetTicks.SetIntLimits(1, 2000);

        InputM5StopTicks.Name = "M5 Stop Ticks";
        InputM5StopTicks.SetInt(50);
        InputM5StopTicks.SetIntLimits(1, 500);

        InputM5TargetTicks.Name = "M5 Target Ticks";
        InputM5TargetTicks.SetInt(120);
        InputM5TargetTicks.SetIntLimits(1, 2000);

        // --- Display inputs (35-39) ---
        InputShowLines.Name = "Show Stop/Target Lines";
        InputShowLines.SetYesNo(1);

        InputShowSkipped.Name = "Show Skipped Signals";
        InputShowSkipped.SetYesNo(1);

        InputMaxVisibleRays.Name = "Max Signal Rays";
        InputMaxVisibleRays.SetInt(3);
        InputMaxVisibleRays.SetIntLimits(0, 50);

        InputLabelDetail.Name = "Label Detail";
        InputLabelDetail.SetCustomInputStrings("Full;Score Only");
        InputLabelDetail.SetCustomInputIndex(0);

        InputSkipBars.Name = "Skip First N Bars (0=process all)";
        InputSkipBars.SetInt(0);
        InputSkipBars.SetIntLimits(0, 500000);

        InputEnableAlerts.Name = "Enable Alert Sounds";
        InputEnableAlerts.SetYesNo(0);

        InputM1AlertSound.Name = "M1 Alert Sound";
        InputM1AlertSound.SetAlertSoundNumber(0);

        InputM3AlertSound.Name = "M3 Alert Sound";
        InputM3AlertSound.SetAlertSoundNumber(0);

        InputM4AlertSound.Name = "M4 Alert Sound";
        InputM4AlertSound.SetAlertSoundNumber(0);

        InputM5AlertSound.Name = "M5 Alert Sound";
        InputM5AlertSound.SetAlertSoundNumber(0);

        InputCSVPath.Name = "CSV Export Path";
        InputCSVPath.SetPathAndFileName("C:\\Projects\\sierrachart\\analysis\\analyzer_zonereaction\\ZB4_signals.csv");

        InputExportCSV.Name = "Export Touch CSV";
        InputExportCSV.SetYesNo(0);

        InputSuppressLabels.Name = "Suppress All Labels";
        InputSuppressLabels.SetYesNo(1);

        // --- Subgraphs ---
        SG_M1Demand.Name = "M1F Demand Entry";
        SG_M1Demand.DrawStyle = DRAWSTYLE_ARROW_UP;
        SG_M1Demand.PrimaryColor = RGB(0, 120, 255);
        SG_M1Demand.LineWidth = 5;
        SG_M1Demand.DrawZeros = false;

        SG_M1Supply.Name = "M1F Supply Entry";
        SG_M1Supply.DrawStyle = DRAWSTYLE_ARROW_DOWN;
        SG_M1Supply.PrimaryColor = RGB(200, 0, 0);
        SG_M1Supply.LineWidth = 5;
        SG_M1Supply.DrawZeros = false;

        SG_M3Demand.Name = "M3 Demand Entry";
        SG_M3Demand.DrawStyle = DRAWSTYLE_ARROW_UP;
        SG_M3Demand.PrimaryColor = RGB(255, 140, 0);
        SG_M3Demand.LineWidth = 5;
        SG_M3Demand.DrawZeros = false;

        SG_M3Supply.Name = "M3 Supply Entry";
        SG_M3Supply.DrawStyle = DRAWSTYLE_ARROW_DOWN;
        SG_M3Supply.PrimaryColor = RGB(200, 0, 200);
        SG_M3Supply.LineWidth = 5;
        SG_M3Supply.DrawZeros = false;

        SG_M4Demand.Name = "M4 Demand Entry";
        SG_M4Demand.DrawStyle = DRAWSTYLE_ARROW_UP;
        SG_M4Demand.PrimaryColor = RGB(128, 128, 128);
        SG_M4Demand.LineWidth = 4;
        SG_M4Demand.DrawZeros = false;

        SG_M4Supply.Name = "M4 Supply Entry";
        SG_M4Supply.DrawStyle = DRAWSTYLE_ARROW_DOWN;
        SG_M4Supply.PrimaryColor = RGB(128, 128, 128);
        SG_M4Supply.LineWidth = 4;
        SG_M4Supply.DrawZeros = false;

        SG_SkipDemand.Name = "Skip Demand Touch";
        SG_SkipDemand.DrawStyle = DRAWSTYLE_ARROW_UP;
        SG_SkipDemand.PrimaryColor = RGB(128, 128, 128);
        SG_SkipDemand.LineWidth = 3;
        SG_SkipDemand.DrawZeros = false;

        SG_SkipSupply.Name = "Skip Supply Touch";
        SG_SkipSupply.DrawStyle = DRAWSTYLE_ARROW_DOWN;
        SG_SkipSupply.PrimaryColor = RGB(128, 128, 128);
        SG_SkipSupply.LineWidth = 3;
        SG_SkipSupply.DrawZeros = false;

        SG_M5Demand.Name = "M5 Demand Entry";
        SG_M5Demand.DrawStyle = DRAWSTYLE_ARROW_UP;
        SG_M5Demand.PrimaryColor = RGB(0, 180, 80);
        SG_M5Demand.LineWidth = 4;
        SG_M5Demand.DrawZeros = false;

        SG_M5Supply.Name = "M5 Supply Entry";
        SG_M5Supply.DrawStyle = DRAWSTYLE_ARROW_DOWN;
        SG_M5Supply.PrimaryColor = RGB(180, 200, 0);
        SG_M5Supply.LineWidth = 4;
        SG_M5Supply.DrawZeros = false;

        // Trend context bar coloring -- tints price bars by trend direction
        SG_TrendSlope.Name = "Trend Bar Color";
        SG_TrendSlope.DrawStyle = DRAWSTYLE_COLOR_BAR;
        SG_TrendSlope.PrimaryColor = RGB(0, 120, 255);    // uptrend color
        SG_TrendSlope.SecondaryColor = RGB(200, 0, 0);    // downtrend color
        SG_TrendSlope.SecondaryColorUsed = 1;
        SG_TrendSlope.DrawZeros = false;

        // Trend slope value -- data-only subgraph for inspection in data window
        SG_TrendZero.Name = "Trend Slope (Ticks)";
        SG_TrendZero.DrawStyle = DRAWSTYLE_IGNORE;
        SG_TrendZero.DrawZeros = false;

        // M1H (Half) — separate subgraphs so ATS can apply different stop/target
        SG_M1HDemand.Name = "M1H Demand Entry";
        SG_M1HDemand.DrawStyle = DRAWSTYLE_ARROW_UP;
        SG_M1HDemand.PrimaryColor = RGB(100, 160, 255);
        SG_M1HDemand.LineWidth = 4;
        SG_M1HDemand.DrawZeros = false;

        SG_M1HSupply.Name = "M1H Supply Entry";
        SG_M1HSupply.DrawStyle = DRAWSTYLE_ARROW_DOWN;
        SG_M1HSupply.PrimaryColor = RGB(255, 80, 80);
        SG_M1HSupply.LineWidth = 4;
        SG_M1HSupply.DrawZeros = false;

        return;
    }

    // === LAST CALL CLEANUP ===

    if (sc.LastCallToFunction)
    {
        SignalStorage* p = (SignalStorage*)sc.GetPersistentPointer(kStoragePtr);
        if (p != nullptr)
        {
            DeleteAllSignalDrawings(sc, MAX_TRACKED_SIGNALS);
            sc.FreeMemory(p);
            sc.SetPersistentPointer(kStoragePtr, nullptr);
        }
        return;
    }

    // === PERSISTENT STORAGE ===

    SignalStorage* pStorage = GetOrAllocateStorage(sc);
    if (pStorage == nullptr)
        return;

    int index = sc.Index;

    // === FULL RECALC RESET ===

    if (sc.UpdateStartIndex == 0 && index == 0)
    {
        DeleteAllSignalDrawings(sc, MAX_TRACKED_SIGNALS);
        pStorage->SignalCount  = 0;
        pStorage->ZoneCount   = 0;
        pStorage->LastBreakBar = 0;
        pStorage->LastHeldBar  = 0;
        memset(pStorage->Signals, 0, sizeof(pStorage->Signals));
        memset(pStorage->Zones, 0, sizeof(pStorage->Zones));

        // Open CSV in write mode (truncate) and write header
        if (InputExportCSV.GetYesNo())
        {
            FILE* fp = fopen(InputCSVPath.GetPathAndFileName(), "w");
            if (fp)
            {
                fprintf(fp, "DateTime,BarIndex,TouchType,ApproachDir,TouchPrice,ZoneTop,ZoneBot,"
                            "HasVPRay,VPRayPrice,ZoneWidthTicks,PenetrationTicks,"
                            "TouchSequence,ZoneAgeBars,ApproachVelocity,TrendSlope,"
                            "SourceLabel,TFWeightScore,TFConfluence,"
                            "CascadeState,CascadeActive,"
                            "SessionClass,DayOfWeek,"
                            "ModeAssignment,QualityScore,ContextScore,TotalScore,"
                            "SourceSlot,ConfirmedBar,HtfConfirmed,Active\n");
                fclose(fp);
            }
        }

        // DEBUG: test file write
        {
            FILE* test = fopen("C:\\Projects\\sierrachart\\zb4_csv_test.txt", "w");
            if (test)
            {
                fprintf(test, "CSV header write attempted. exportCSV=%d path=%s\n",
                        InputExportCSV.GetYesNo() ? 1 : 0,
                        InputCSVPath.GetPathAndFileName());
                fclose(test);
            }
        }
    }

    if (index < 1)
        return;

    bool isLiveBar = (index == sc.ArraySize - 1);

    // === READ INPUTS ===

    int activeCount = InputActiveCount.GetInt();
    if (activeCount < 1) activeCount = 1;
    if (activeCount > MAX_CHART_SLOTS) activeCount = MAX_CHART_SLOTS;

    int m1FullThreshold = InputM1FullThreshold.GetInt();
    int m1HalfThreshold = InputM1HalfThreshold.GetInt();
    int maxSeq          = InputMaxTouchSeq.GetInt();
    float trendThr      = (float)InputTrendThreshold.GetInt();
    float confluenceTol = InputConfluenceTol.GetInt() * sc.TickSize;
    bool showLines      = InputShowLines.GetYesNo() != 0;
    int  maxVisibleRays = InputMaxVisibleRays.GetInt();
    int  skipBars       = InputSkipBars.GetInt();
    bool gradeOnly      = (InputLabelDetail.GetIndex() == 1);
    int  fastPeriod     = InputFastEMAPeriod.GetInt();
    int  slowPeriod     = InputSlowEMAPeriod.GetInt();
    bool useEMA         = (InputTrendMethod.GetIndex() == 1);
    int  slopeLookback  = InputSlopeLookback.GetInt();
    int  m3Stop         = InputM3StopTicks.GetInt();
    int  m3Target       = InputM3TargetTicks.GetInt();
    int  m4Stop         = InputM4StopTicks.GetInt();
    int  m4Target       = InputM4TargetTicks.GetInt();
    int  m5Stop         = InputM5StopTicks.GetInt();
    int  m5Target       = InputM5TargetTicks.GetInt();
    int  cascadeWindow  = InputCascadeWindow.GetInt();
    bool showSkipped    = InputShowSkipped.GetYesNo() != 0;
    bool exportCSV      = InputExportCSV.GetYesNo() != 0;
    bool suppressLabels = InputSuppressLabels.GetYesNo() != 0;
    bool alertsEnabled  = InputEnableAlerts.GetYesNo() != 0;
    unsigned int m1Sound = InputM1AlertSound.GetAlertSoundNumber();
    unsigned int m3Sound = InputM3AlertSound.GetAlertSoundNumber();
    unsigned int m4Sound = InputM4AlertSound.GetAlertSoundNumber();
    unsigned int m5Sound = InputM5AlertSound.GetAlertSoundNumber();
    float tickSize      = sc.TickSize;

    // === SKIP EARLY BARS ===
    if (skipBars > 0 && index < skipBars)
        return;

    // === CLEAR SUBGRAPHS ===

    SG_M1Demand[index]   = 0;
    SG_M1Supply[index]   = 0;
    SG_M1HDemand[index]  = 0;
    SG_M1HSupply[index]  = 0;
    SG_M3Demand[index]   = 0;
    SG_M3Supply[index]   = 0;
    SG_M4Demand[index]   = 0;
    SG_M4Supply[index]   = 0;
    SG_M5Demand[index]   = 0;
    SG_M5Supply[index]   = 0;
    SG_SkipDemand[index] = 0;
    SG_SkipSupply[index] = 0;

    // === TREND OUTPUT ===

    SCFloatArrayRef fastEMA = SG_TrendSlope.Arrays[0];
    SCFloatArrayRef slowEMA = SG_TrendSlope.Arrays[1];

    float trendValue;
    if (useEMA)
    {
        sc.ExponentialMovAvg(sc.BaseData[SC_LAST], fastEMA, index, fastPeriod);
        sc.ExponentialMovAvg(sc.BaseData[SC_LAST], slowEMA, index, slowPeriod);
        trendValue = (fastEMA[index] - slowEMA[index]) / tickSize;
    }
    else
    {
        trendValue = CalcTrendSlope(sc, index, tickSize, slopeLookback);
    }
    SG_TrendZero[index] = trendValue;

    if (trendValue > trendThr)
    {
        SG_TrendSlope[index] = 1;
        SG_TrendSlope.DataColor[index] = RGB(0, 120, 255);
    }
    else if (trendValue < -trendThr)
    {
        SG_TrendSlope[index] = 1;
        SG_TrendSlope.DataColor[index] = RGB(200, 0, 0);
    }
    else
    {
        SG_TrendSlope[index] = 0;
    }

    // === BUILD CHART SLOT TABLE AND FETCH V4 ARRAYS ===

    ChartSlotData slots[MAX_CHART_SLOTS];
    memset(slots, 0, sizeof(slots));

    for (int s = 0; s < activeCount; s++)
    {
        int inputBase = 1 + s * 2;
        slots[s].ChartNumber = sc.Input[inputBase].GetInt();
        slots[s].StudyID     = sc.Input[inputBase + 1].GetInt();
        FetchChartSlot(sc, slots[s], index);
    }

    // === CASCADE TRACKING ===
    for (int s = 0; s < activeCount; s++)
    {
        if (!slots[s].Valid)
            continue;
        int htfIdx = slots[s].V4Idx;
        if (slots[s].DemandBroken.GetArraySize() > htfIdx && htfIdx >= 0)
        {
            if (slots[s].DemandBroken[htfIdx] > 0)
                pStorage->LastBreakBar = index;
        }
        if (slots[s].SupplyBroken.GetArraySize() > htfIdx && htfIdx >= 0)
        {
            if (slots[s].SupplyBroken[htfIdx] > 0)
                pStorage->LastBreakBar = index;
        }
    }

    // === DIAGNOSTIC FILE (last bar only) ===
    if (index == sc.ArraySize - 1)
    {
        FILE* fp = fopen("C:\\Projects\\sierrachart\\zbsv2_diag.txt", "w");
        if (fp)
        {
            int validCount = 0;
            for (int s = 0; s < activeCount; s++)
                if (slots[s].Valid) validCount++;

            fprintf(fp, "ZBSv2 Diagnostics (last bar)\n");
            fprintf(fp, "bar=%d  arraySize=%d  activeSlots=%d  validSlots=%d\n",
                    index, sc.ArraySize, activeCount, validCount);
            fprintf(fp, "signals=%d  zones=%d  tickSize=%.4f\n",
                    pStorage->SignalCount, pStorage->ZoneCount, tickSize);
            fprintf(fp, "trendVal=%.1f  threshold=%.1f  method=%s  fastPeriod=%d  slowPeriod=%d\n",
                    trendValue, trendThr, useEMA ? "EMA" : "Slope", fastPeriod, slowPeriod);
            fprintf(fp, "m1FullThr=%d  m1HalfThr=%d  cascadeWindow=%d  lastBreak=%d  lastHeld=%d\n\n",
                    m1FullThreshold, m1HalfThreshold, cascadeWindow,
                    pStorage->LastBreakBar, pStorage->LastHeldBar);

            for (int s = 0; s < activeCount; s++)
            {
                fprintf(fp, "slot[%d]: chart=%d study=%d valid=%s tfWeight=%d",
                        s, slots[s].ChartNumber, slots[s].StudyID,
                        slots[s].Valid ? "YES" : "NO",
                        slots[s].TFWeightScore);
                if (slots[s].Valid)
                {
                    fprintf(fp, " v4Size=%d v4Idx=%d dTop=%.2f dBot=%.2f sBot=%.2f sTop=%.2f",
                            slots[s].V4Size, slots[s].V4Idx,
                            slots[s].DemandTop[slots[s].V4Idx],
                            slots[s].DemandBot[slots[s].V4Idx],
                            slots[s].SupplyBot[slots[s].V4Idx],
                            slots[s].SupplyTop[slots[s].V4Idx]);
                }
                else
                {
                    fprintf(fp, " arrSize=%d", slots[s].DemandTop.GetArraySize());
                }
                fprintf(fp, "\n");
            }

            fprintf(fp, "\nLast zones (up to 20):\n");
            int zStart = pStorage->ZoneCount > 20 ? pStorage->ZoneCount - 20 : 0;
            for (int i = zStart; i < pStorage->ZoneCount; i++)
            {
                TrackedZone& z = pStorage->Zones[i];
                fprintf(fp, "  [%d] %s slot=%d top=%.2f bot=%.2f firstBar=%d birthHtf=%d touches=%d\n",
                        i, z.IsDemand ? "DEM" : "SUP", z.SlotIdx,
                        z.Top, z.Bot, z.FirstSeenBar, z.FirstSeenHtfBar, z.TouchCount);
            }

            fprintf(fp, "\nLast signals (up to 10):\n");
            int start = pStorage->SignalCount > 10 ? pStorage->SignalCount - 10 : 0;
            for (int i = start; i < pStorage->SignalCount; i++)
            {
                SignalRecord& sig = pStorage->Signals[i];
                const char* modeStr = ModeLabel(sig.ModeAssignment);
                fprintf(fp, "  [%d] bar=%d cBar=%d type=%s price=%.2f seq=%d trend=%s mode=%s total=%d(q=%d+c=%d) tf=%d tfW=%d sess=%d dow=%d casc=%d slot=%d htfBar=%d confirmed=%s\n",
                        i, sig.BarIndex, sig.ConfirmedBar,
                        sig.Type == kDemandEdge ? "DEM" : "SUP",
                        sig.TouchPrice, sig.TouchSequence,
                        sig.TrendCtx == kWithTrend ? "WT" :
                          (sig.TrendCtx == kCounterTrend ? "CT" : "NT"),
                        modeStr, sig.TotalScore, sig.QualityScore, sig.ContextScore,
                        sig.TFConfluence, sig.TFWeightScore,
                        sig.SessionClass, sig.DayOfWeek, sig.CascadeState,
                        sig.SourceSlot, sig.SourceHtfBar,
                        sig.HtfConfirmed ? "YES" : "NO");
                fprintf(fp, "        pen=%.0ft vel=%.0ft zoneW=%.0ft age=%d prevPrice=%.2f prevZone=%.2f evalPrice=%.2f evalZone=%.2f\n",
                        sig.PenetrationTicks, sig.ApproachVelocity,
                        sig.ZoneWidthTicks, sig.ZoneAgeBars,
                        sig.DbgPrevHigh, sig.DbgPrevSBot,
                        sig.DbgEvalHigh, sig.DbgEvalSBot);
            }

            fclose(fp);
        }

    }

    // === ZONE DISCOVERY (register zones before touch detection) ===

    if (index >= 1 && !isLiveBar)
    for (int s = 0; s < activeCount; s++)
    {
        if (!slots[s].Valid)
            continue;

        float dTop = slots[s].DemandTop[slots[s].V4Idx];
        float dBot = slots[s].DemandBot[slots[s].V4Idx];
        float sTop = slots[s].SupplyTop[slots[s].V4Idx];
        float sBot = slots[s].SupplyBot[slots[s].V4Idx];

        if (dTop > 0 && dBot > 0)
            FindOrCreateZone(pStorage, dTop, dBot, true, s, index, slots[s].V4Idx, 0.01f);
        if (sTop > 0 && sBot > 0)
            FindOrCreateZone(pStorage, sTop, sBot, false, s, index, slots[s].V4Idx, 0.01f);
    }

    // === TOUCH DETECTION (per chart slot) ===
    // Evaluate current bar (index) against previous bar (index-1) to match ZRA.
    // Skip the live forming bar to avoid evaluating incomplete data.

    if (index >= 1 && !isLiveBar)
    for (int s = 0; s < activeCount; s++)
    {
        if (!slots[s].Valid)
            continue;

        int evalBar = index;
        int prevBar = index - 1;

        float low   = sc.Low[evalBar];
        float high  = sc.High[evalBar];
        float low1  = sc.Low[prevBar];
        float high1 = sc.High[prevBar];

        float dTop  = slots[s].DemandTop[slots[s].V4Idx];
        float dBot  = slots[s].DemandBot[slots[s].V4Idx];
        float sTop  = slots[s].SupplyTop[slots[s].V4Idx];
        float sBot  = slots[s].SupplyBot[slots[s].V4Idx];
        float vpRay = (slots[s].VPImbalance.GetArraySize() > 0)
                      ? slots[s].VPImbalance[slots[s].V4Idx] : 0.0f;

        float dTop1 = slots[s].DemandTop[slots[s].V4Idx1];
        float sBot1 = slots[s].SupplyBot[slots[s].V4Idx1];

        bool vpActive = (vpRay > 0.0f);

        // --- DEMAND_EDGE ---
        if (dTop > 0 && dBot > 0)
        {
            bool zoneConsistent = (dTop1 > 0 && fabs(dTop - dTop1) < tickSize * 2);
            bool touchNow       = (low <= dTop);
            bool notTouchBefore = (low1 > dTop1);

            if (zoneConsistent && touchNow && notTouchBefore)
            {
                int zoneIdx = FindOrCreateZone(pStorage, dTop, dBot, true, s, evalBar, slots[s].V4Idx, 0.01f);

                bool demDebounced = IsDebouncedDuplicate(pStorage, kDemandEdge, dTop, tickSize, evalBar, s);
                if (!demDebounced)
                {
                    {
                        int seq = 1, ageBars = 0;
                        if (zoneIdx >= 0)
                        {
                            pStorage->Zones[zoneIdx].TouchCount++;
                            seq     = pStorage->Zones[zoneIdx].TouchCount;
                            ageBars = evalBar - pStorage->Zones[zoneIdx].FirstSeenBar;
                        }

                        float slope  = useEMA
                            ? (fastEMA[evalBar] - slowEMA[evalBar]) / tickSize
                            : CalcTrendSlope(sc, evalBar, tickSize, slopeLookback);
                        int trendCtx = ClassifyTrend(kDemandEdge, slope, trendThr);
                        int tfCount  = CountTFConfluence(slots, activeCount,
                                                         kDemandEdge, dTop, confluenceTol, s);

                        float approachVel  = CalcApproachVelocity(sc, evalBar, tickSize);
                        float zoneWidth    = fabs(dTop - dBot) / tickSize;
                        float penetration  = CalcPenetrationTicks(kDemandEdge, dTop, low, high, tickSize);

                        int sessionCls = ClassifySession(
                            sc.BaseDateTimeIn[evalBar].GetHour(),
                            sc.BaseDateTimeIn[evalBar].GetMinute());
                        int dow = sc.BaseDateTimeIn[evalBar].GetDayOfWeek();
                        int cascState = DetermineCascadeState(evalBar,
                            pStorage->LastBreakBar, pStorage->LastHeldBar, cascadeWindow);

                        int qualityScore = CalcZoneQualityScore(
                            slots[s].TFWeightScore, zoneWidth, vpActive);
                        int contextScore = CalcContextScore(
                            cascState, sessionCls, approachVel, penetration);
                        int totalScore = qualityScore + contextScore;

                        bool seqOk   = (seq <= maxSeq);
                        bool trendOk = (trendCtx == kWithTrend);
                        bool isQualified = seqOk && trendOk;
                        bool isRejected  = seqOk && !trendOk;

                        int mode;
                        if (isQualified && totalScore >= m1FullThreshold)
                            mode = kMode1Full;
                        else if (isQualified && totalScore >= m1HalfThreshold)
                            mode = kMode1Half;
                        else if (isRejected)
                            mode = kMode3;
                        else if (sessionCls == kAfternoon)
                            mode = kMode4;
                        else
                            mode = kMode5;

                        if (pStorage->SignalCount >= MAX_TRACKED_SIGNALS)
                            EvictOldSignals(sc, pStorage);

                        if (pStorage->SignalCount < MAX_TRACKED_SIGNALS)
                        {
                        SignalRecord& sig = pStorage->Signals[pStorage->SignalCount];
                        sig.TouchPrice       = dTop;
                        sig.ZoneTop          = dTop;
                        sig.ZoneBot          = dBot;
                        sig.TrendSlope       = slope;
                        sig.VPRayPrice       = vpRay;
                        sig.BarIndex         = evalBar;
                        sig.TouchSequence    = seq;
                        sig.Type             = kDemandEdge;
                        sig.TrendCtx         = trendCtx;
                        sig.ModeAssignment   = mode;
                        sig.QualityScore     = qualityScore;
                        sig.ContextScore     = contextScore;
                        sig.TotalScore       = totalScore;
                        sig.TFConfluence     = tfCount;
                        sig.ApproachVelocity = approachVel;
                        sig.ZoneWidthTicks   = zoneWidth;
                        sig.ZoneAgeBars      = ageBars;
                        sig.PenetrationTicks = penetration;
                        sig.TFWeightScore    = slots[s].TFWeightScore;
                        sig.SessionClass     = sessionCls;
                        sig.DayOfWeek        = dow;
                        sig.CascadeState     = cascState;
                        sig.SourceSlot       = s;
                        sig.SourceHtfBar     = slots[s].V4Idx;
                        sig.ConfirmedBar     = evalBar;
                        sig.DbgPrevHigh      = low1;
                        sig.DbgPrevSBot      = dTop1;
                        sig.DbgEvalHigh      = low;
                        sig.DbgEvalSBot      = dTop;
                        sig.HasVPRay         = vpActive;
                        sig.CascadeActive    = (cascState == kCascadePriorBroke);
                        sig.HtfConfirmed     = true;
                        sig.DrawingsPlaced   = false;
                        sig.RaysResolved     = false;
                        sig.Active           = true;
                        pStorage->SignalCount++;

                        // Incremental CSV export
                        if (exportCSV)
                        {
                            FILE* fp = fopen(InputCSVPath.GetPathAndFileName(), "a");
                            if (fp)
                            {
                                const SignalRecord& csvSig = pStorage->Signals[pStorage->SignalCount - 1];

                                SCDateTime dt = sc.BaseDateTimeIn[csvSig.BarIndex];
                                int yr, mo, dy, hr, mn, sc2;
                                dt.GetDateTimeYMDHMS(yr, mo, dy, hr, mn, sc2);

                                const char* ttStr;
                                switch (csvSig.Type)
                                {
                                    case 0:  ttStr = "DEMAND_EDGE"; break;
                                    case 1:  ttStr = "SUPPLY_EDGE"; break;
                                    default: ttStr = "UNKNOWN";     break;
                                }

                                int appDir = (csvSig.Type == 0) ? -1 : 1;

                                const char* srcLabel;
                                {
                                    int ii = 1 + csvSig.SourceSlot * 2;
                                    int cn = sc.Input[ii].GetInt();
                                    n_ACSIL::s_BarPeriod bp;
                                    sc.GetBarPeriodParametersForChart(cn, bp);
                                    int mins = bp.IntradayChartBarPeriodParameter1 / 60;
                                    if (mins >= 720)      srcLabel = "720m";
                                    else if (mins >= 480) srcLabel = "480m";
                                    else if (mins >= 360) srcLabel = "360m";
                                    else if (mins >= 240) srcLabel = "240m";
                                    else if (mins >= 120) srcLabel = "120m";
                                    else if (mins >= 90)  srcLabel = "90m";
                                    else if (mins >= 60)  srcLabel = "60m";
                                    else if (mins >= 30)  srcLabel = "30m";
                                    else if (mins >= 15)  srcLabel = "15m";
                                    else                  srcLabel = "??m";
                                }

                                const char* cascStr;
                                switch (csvSig.CascadeState)
                                {
                                    case kCascadePriorHeld:  cascStr = "PRIOR_HELD";  break;
                                    case kCascadeNoPrior:    cascStr = "NO_PRIOR";    break;
                                    case kCascadePriorBroke: cascStr = "PRIOR_BROKE"; break;
                                    default:                cascStr = "UNKNOWN";      break;
                                }

                                const char* mStr = ModeLabel(csvSig.ModeAssignment);

                                fprintf(fp, "%d/%d/%d %d:%02d,"
                                            "%d,%s,%d,"
                                            "%.2f,%.2f,%.2f,"
                                            "%d,%.2f,"
                                            "%.0f,%.0f,"
                                            "%d,%d,"
                                            "%.1f,%.4f,"
                                            "%s,%d,%d,"
                                            "%s,%d,"
                                            "%d,%d,"
                                            "%s,%d,%d,%d,"
                                            "%d,%d,%d,%d\n",
                                        mo, dy, yr, hr, mn,
                                        csvSig.BarIndex, ttStr, appDir,
                                        csvSig.TouchPrice, csvSig.ZoneTop, csvSig.ZoneBot,
                                        csvSig.HasVPRay ? 1 : 0, csvSig.VPRayPrice,
                                        csvSig.ZoneWidthTicks, csvSig.PenetrationTicks,
                                        csvSig.TouchSequence, csvSig.ZoneAgeBars,
                                        csvSig.ApproachVelocity, csvSig.TrendSlope,
                                        srcLabel, csvSig.TFWeightScore, csvSig.TFConfluence,
                                        cascStr, csvSig.CascadeActive ? 1 : 0,
                                        csvSig.SessionClass, csvSig.DayOfWeek,
                                        mStr, csvSig.QualityScore, csvSig.ContextScore, csvSig.TotalScore,
                                        csvSig.SourceSlot, csvSig.ConfirmedBar,
                                        csvSig.HtfConfirmed ? 1 : 0, 1);
                                fclose(fp);
                            }
                        }
                        }

                        if (mode != kSkip)
                            pStorage->LastHeldBar = evalBar;

                        if (!suppressLabels)
                        {
                        float arrowY = sc.Low[evalBar] - (15 * tickSize);
                        switch (mode)
                        {
                            case kMode1Full:
                                SG_M1Demand[evalBar] = arrowY;
                                break;
                            case kMode1Half:
                                SG_M1HDemand[evalBar] = arrowY;
                                break;
                            case kMode3:
                                SG_M3Demand[evalBar] = arrowY;
                                break;
                            case kMode4:
                                SG_M4Demand[evalBar] = arrowY;
                                break;
                            case kMode5:
                                SG_M5Demand[evalBar] = arrowY;
                                break;
                            case kSkip:
                                if (showSkipped)
                                    SG_SkipDemand[evalBar] = arrowY;
                                break;
                        }
                        }

                        if (isLiveBar && alertsEnabled)
                            PlayModeAlert(sc, mode, kDemandEdge, seq, totalScore,
                                          m1Sound, m3Sound, m4Sound, m5Sound);
                    }
                }
            }
        }
        // --- SUPPLY_EDGE ---
        if (sTop > 0 && sBot > 0)
        {
            bool zoneConsistent = (sBot1 > 0 && fabs(sBot - sBot1) < tickSize * 2);
            bool touchNow       = (high >= sBot);
            bool notTouchBefore = (high1 < sBot1);

            if (zoneConsistent && touchNow && notTouchBefore)
            {
                int zoneIdx = FindOrCreateZone(pStorage, sTop, sBot, false, s, evalBar, slots[s].V4Idx, 0.01f);

                bool supDebounced = IsDebouncedDuplicate(pStorage, kSupplyEdge, sBot, tickSize, evalBar, s);
                if (!supDebounced)
                {
                    {
                        int seq = 1, ageBars = 0;
                        if (zoneIdx >= 0)
                        {
                            pStorage->Zones[zoneIdx].TouchCount++;
                            seq     = pStorage->Zones[zoneIdx].TouchCount;
                            ageBars = evalBar - pStorage->Zones[zoneIdx].FirstSeenBar;
                        }

                        float slope  = useEMA
                            ? (fastEMA[evalBar] - slowEMA[evalBar]) / tickSize
                            : CalcTrendSlope(sc, evalBar, tickSize, slopeLookback);
                        int trendCtx = ClassifyTrend(kSupplyEdge, slope, trendThr);
                        int tfCount  = CountTFConfluence(slots, activeCount,
                                                         kSupplyEdge, sBot, confluenceTol, s);

                        float approachVel  = CalcApproachVelocity(sc, evalBar, tickSize);
                        float zoneWidth    = fabs(sTop - sBot) / tickSize;
                        float penetration  = CalcPenetrationTicks(kSupplyEdge, sBot, low, high, tickSize);

                        int sessionCls = ClassifySession(
                            sc.BaseDateTimeIn[evalBar].GetHour(),
                            sc.BaseDateTimeIn[evalBar].GetMinute());
                        int dow = sc.BaseDateTimeIn[evalBar].GetDayOfWeek();
                        int cascState = DetermineCascadeState(evalBar,
                            pStorage->LastBreakBar, pStorage->LastHeldBar, cascadeWindow);

                        int qualityScore = CalcZoneQualityScore(
                            slots[s].TFWeightScore, zoneWidth, vpActive);
                        int contextScore = CalcContextScore(
                            cascState, sessionCls, approachVel, penetration);
                        int totalScore = qualityScore + contextScore;

                        bool seqOk   = (seq <= maxSeq);
                        bool trendOk = (trendCtx == kWithTrend);
                        bool isQualified = seqOk && trendOk;
                        bool isRejected  = seqOk && !trendOk;

                        int mode;
                        if (isQualified && totalScore >= m1FullThreshold)
                            mode = kMode1Full;
                        else if (isQualified && totalScore >= m1HalfThreshold)
                            mode = kMode1Half;
                        else if (isRejected)
                            mode = kMode3;
                        else if (sessionCls == kAfternoon)
                            mode = kMode4;
                        else
                            mode = kMode5;

                        if (pStorage->SignalCount >= MAX_TRACKED_SIGNALS)
                            EvictOldSignals(sc, pStorage);

                        if (pStorage->SignalCount < MAX_TRACKED_SIGNALS)
                        {
                        SignalRecord& sig = pStorage->Signals[pStorage->SignalCount];
                        sig.TouchPrice       = sBot;
                        sig.ZoneTop          = sTop;
                        sig.ZoneBot          = sBot;
                        sig.TrendSlope       = slope;
                        sig.VPRayPrice       = vpRay;
                        sig.BarIndex         = evalBar;
                        sig.TouchSequence    = seq;
                        sig.Type             = kSupplyEdge;
                        sig.TrendCtx         = trendCtx;
                        sig.ModeAssignment   = mode;
                        sig.QualityScore     = qualityScore;
                        sig.ContextScore     = contextScore;
                        sig.TotalScore       = totalScore;
                        sig.TFConfluence     = tfCount;
                        sig.ApproachVelocity = approachVel;
                        sig.ZoneWidthTicks   = zoneWidth;
                        sig.ZoneAgeBars      = ageBars;
                        sig.PenetrationTicks = penetration;
                        sig.TFWeightScore    = slots[s].TFWeightScore;
                        sig.SessionClass     = sessionCls;
                        sig.DayOfWeek        = dow;
                        sig.CascadeState     = cascState;
                        sig.SourceSlot       = s;
                        sig.SourceHtfBar     = slots[s].V4Idx;
                        sig.ConfirmedBar     = evalBar;
                        sig.DbgPrevHigh      = high1;
                        sig.DbgPrevSBot      = sBot1;
                        sig.DbgEvalHigh      = high;
                        sig.DbgEvalSBot      = sBot;
                        sig.HasVPRay         = vpActive;
                        sig.CascadeActive    = (cascState == kCascadePriorBroke);
                        sig.HtfConfirmed     = true;
                        sig.DrawingsPlaced   = false;
                        sig.RaysResolved     = false;
                        sig.Active           = true;
                        pStorage->SignalCount++;

                        // Incremental CSV export
                        if (exportCSV)
                        {
                            FILE* fp = fopen(InputCSVPath.GetPathAndFileName(), "a");
                            if (fp)
                            {
                                const SignalRecord& csvSig = pStorage->Signals[pStorage->SignalCount - 1];

                                SCDateTime dt = sc.BaseDateTimeIn[csvSig.BarIndex];
                                int yr, mo, dy, hr, mn, sc2;
                                dt.GetDateTimeYMDHMS(yr, mo, dy, hr, mn, sc2);

                                const char* ttStr;
                                switch (csvSig.Type)
                                {
                                    case 0:  ttStr = "DEMAND_EDGE"; break;
                                    case 1:  ttStr = "SUPPLY_EDGE"; break;
                                    default: ttStr = "UNKNOWN";     break;
                                }

                                int appDir = (csvSig.Type == 0) ? -1 : 1;

                                const char* srcLabel;
                                {
                                    int ii = 1 + csvSig.SourceSlot * 2;
                                    int cn = sc.Input[ii].GetInt();
                                    n_ACSIL::s_BarPeriod bp;
                                    sc.GetBarPeriodParametersForChart(cn, bp);
                                    int mins = bp.IntradayChartBarPeriodParameter1 / 60;
                                    if (mins >= 720)      srcLabel = "720m";
                                    else if (mins >= 480) srcLabel = "480m";
                                    else if (mins >= 360) srcLabel = "360m";
                                    else if (mins >= 240) srcLabel = "240m";
                                    else if (mins >= 120) srcLabel = "120m";
                                    else if (mins >= 90)  srcLabel = "90m";
                                    else if (mins >= 60)  srcLabel = "60m";
                                    else if (mins >= 30)  srcLabel = "30m";
                                    else if (mins >= 15)  srcLabel = "15m";
                                    else                  srcLabel = "??m";
                                }

                                const char* cascStr;
                                switch (csvSig.CascadeState)
                                {
                                    case kCascadePriorHeld:  cascStr = "PRIOR_HELD";  break;
                                    case kCascadeNoPrior:    cascStr = "NO_PRIOR";    break;
                                    case kCascadePriorBroke: cascStr = "PRIOR_BROKE"; break;
                                    default:                cascStr = "UNKNOWN";      break;
                                }

                                const char* mStr = ModeLabel(csvSig.ModeAssignment);

                                fprintf(fp, "%d/%d/%d %d:%02d,"
                                            "%d,%s,%d,"
                                            "%.2f,%.2f,%.2f,"
                                            "%d,%.2f,"
                                            "%.0f,%.0f,"
                                            "%d,%d,"
                                            "%.1f,%.4f,"
                                            "%s,%d,%d,"
                                            "%s,%d,"
                                            "%d,%d,"
                                            "%s,%d,%d,%d,"
                                            "%d,%d,%d,%d\n",
                                        mo, dy, yr, hr, mn,
                                        csvSig.BarIndex, ttStr, appDir,
                                        csvSig.TouchPrice, csvSig.ZoneTop, csvSig.ZoneBot,
                                        csvSig.HasVPRay ? 1 : 0, csvSig.VPRayPrice,
                                        csvSig.ZoneWidthTicks, csvSig.PenetrationTicks,
                                        csvSig.TouchSequence, csvSig.ZoneAgeBars,
                                        csvSig.ApproachVelocity, csvSig.TrendSlope,
                                        srcLabel, csvSig.TFWeightScore, csvSig.TFConfluence,
                                        cascStr, csvSig.CascadeActive ? 1 : 0,
                                        csvSig.SessionClass, csvSig.DayOfWeek,
                                        mStr, csvSig.QualityScore, csvSig.ContextScore, csvSig.TotalScore,
                                        csvSig.SourceSlot, csvSig.ConfirmedBar,
                                        csvSig.HtfConfirmed ? 1 : 0, 1);
                                fclose(fp);
                            }
                        }
                        }

                        if (mode != kSkip)
                            pStorage->LastHeldBar = evalBar;

                        if (!suppressLabels)
                        {
                        float arrowY = sc.High[evalBar] + (15 * tickSize);
                        switch (mode)
                        {
                            case kMode1Full:
                                SG_M1Supply[evalBar] = arrowY;
                                break;
                            case kMode1Half:
                                SG_M1HSupply[evalBar] = arrowY;
                                break;
                            case kMode3:
                                SG_M3Supply[evalBar] = arrowY;
                                break;
                            case kMode4:
                                SG_M4Supply[evalBar] = arrowY;
                                break;
                            case kMode5:
                                SG_M5Supply[evalBar] = arrowY;
                                break;
                            case kSkip:
                                if (showSkipped)
                                    SG_SkipSupply[evalBar] = arrowY;
                                break;
                        }
                        }

                        if (isLiveBar && alertsEnabled)
                            PlayModeAlert(sc, mode, kSupplyEdge, seq, totalScore,
                                          m1Sound, m3Sound, m4Sound, m5Sound);
                    }
                }
            }
        }
    }

    // === SUBGRAPH RESTORATION PASS ===
    // Re-set arrow subgraph values for confirmed signals on current or previous bar.

    if (!suppressLabels)
    for (int i = 0; i < pStorage->SignalCount; i++)
    {
        SignalRecord& sig = pStorage->Signals[i];
        if (!sig.Active)
            continue;
        if (sig.BarIndex != index && sig.BarIndex != index - 1)
            continue;

        int sigBar = sig.BarIndex;
        bool isDemand = (sig.Type == kDemandEdge);
        float arrowY = isDemand ? (sc.Low[sigBar] - (15 * tickSize))
                                : (sc.High[sigBar] + (15 * tickSize));

        switch (sig.ModeAssignment)
        {
            case kMode1Full:
                if (isDemand) SG_M1Demand[sigBar] = arrowY;
                else          SG_M1Supply[sigBar] = arrowY;
                break;
            case kMode1Half:
                if (isDemand) SG_M1HDemand[sigBar] = arrowY;
                else          SG_M1HSupply[sigBar] = arrowY;
                break;
            case kMode3:
                if (isDemand) SG_M3Demand[sigBar] = arrowY;
                else          SG_M3Supply[sigBar] = arrowY;
                break;
            case kMode4:
                if (isDemand) SG_M4Demand[sigBar] = arrowY;
                else          SG_M4Supply[sigBar] = arrowY;
                break;
            case kMode5:
                if (isDemand) SG_M5Demand[sigBar] = arrowY;
                else          SG_M5Supply[sigBar] = arrowY;
                break;
            case kSkip:
                if (showSkipped)
                {
                    if (isDemand) SG_SkipDemand[sigBar] = arrowY;
                    else          SG_SkipSupply[sigBar] = arrowY;
                }
                break;
        }
    }

    // === DRAWING PLACEMENT PASS ===

    if (!suppressLabels)
    for (int i = 0; i < pStorage->SignalCount; i++)
    {
        SignalRecord& sig = pStorage->Signals[i];
        if (!sig.Active || sig.DrawingsPlaced)
            continue;
        if (sig.BarIndex > index)
            continue;

        bool shouldDraw = (sig.ModeAssignment != kSkip) ||
                          (sig.ModeAssignment == kSkip && showSkipped);
        if (!shouldDraw)
        {
            sig.DrawingsPlaced = true;
            continue;
        }

        PlaceSignalDrawings(sc, sig, i, tickSize,
                            sig.ModeAssignment, sig.TotalScore,
                            m3Stop, m3Target, m4Stop, m4Target,
                            m5Stop, m5Target,
                            showLines, true, gradeOnly);
    }

    // === RAY RESOLUTION PASS ===
    // Delete stop/target rays once price reaches either level.
    // Only resolve during live updates (UpdateStartIndex > 0) so that
    // historical recalculation doesn't immediately delete every ray.
    if (showLines && sc.UpdateStartIndex > 0)
    {
        for (int i = 0; i < pStorage->SignalCount; i++)
        {
            SignalRecord& sig = pStorage->Signals[i];
            if (!sig.Active || !sig.DrawingsPlaced || sig.RaysResolved)
                continue;
            if (sig.ModeAssignment == kSkip)
                continue;
            if (sig.BarIndex >= index)  // need at least one bar after signal
                continue;

            int sigStop, sigTarget;
            GetModeStopTarget(sig.ModeAssignment, sig.ZoneWidthTicks,
                              m3Stop, m3Target, m4Stop, m4Target,
                              m5Stop, m5Target,
                              sigStop, sigTarget);
            if (sigStop == 0) continue; // Skip signals have no rays

            float stopOffset   = sigStop * tickSize;
            float targetOffset = sigTarget * tickSize;

            bool isDemand = (sig.Type == kDemandEdge);
            float stopPrice, targetPrice;
            if (isDemand)
            {
                stopPrice   = sig.TouchPrice - stopOffset;
                targetPrice = sig.TouchPrice + targetOffset;
            }
            else
            {
                stopPrice   = sig.TouchPrice + stopOffset;
                targetPrice = sig.TouchPrice - targetOffset;
            }

            // Check every bar from signal bar+1 through current bar
            bool resolved = false;
            for (int b = sig.BarIndex + 1; b <= index; b++)
            {
                if (isDemand)
                {
                    if (sc.BaseData[SC_LOW][b] <= stopPrice ||
                        sc.BaseData[SC_HIGH][b] >= targetPrice)
                    { resolved = true; break; }
                }
                else
                {
                    if (sc.BaseData[SC_HIGH][b] >= stopPrice ||
                        sc.BaseData[SC_LOW][b] <= targetPrice)
                    { resolved = true; break; }
                }
            }

            if (resolved)
            {
                sc.DeleteACSChartDrawing(sc.ChartNumber,
                    TOOL_DELETE_CHARTDRAWING, LN_BASE_STOP + i);
                sc.DeleteACSChartDrawing(sc.ChartNumber,
                    TOOL_DELETE_CHARTDRAWING, LN_BASE_TARGET + i);
                sig.RaysResolved = true;
            }
        }
    }

    // === RAY LIMIT CLEANUP ===
    // Keep only the most recent maxVisibleRays non-Skip signals with rays.

    if (showLines && maxVisibleRays > 0)
    {
        // Count non-Skip signals with active rays
        int activeRayCount = 0;
        for (int i = pStorage->SignalCount - 1; i >= 0; i--)
        {
            SignalRecord& sig = pStorage->Signals[i];
            if (sig.Active && sig.DrawingsPlaced && !sig.RaysResolved &&
                sig.ModeAssignment != kSkip)
                activeRayCount++;
        }

        // If over the limit, delete rays for the oldest signals
        if (activeRayCount > maxVisibleRays)
        {
            int toRemove = activeRayCount - maxVisibleRays;
            for (int i = 0; i < pStorage->SignalCount && toRemove > 0; i++)
            {
                SignalRecord& sig = pStorage->Signals[i];
                if (sig.Active && sig.DrawingsPlaced && !sig.RaysResolved &&
                    sig.ModeAssignment != kSkip)
                {
                    sc.DeleteACSChartDrawing(sc.ChartNumber, TOOL_DELETE_CHARTDRAWING,
                                             LN_BASE_STOP + i);
                    sc.DeleteACSChartDrawing(sc.ChartNumber, TOOL_DELETE_CHARTDRAWING,
                                             LN_BASE_TARGET + i);
                    sig.RaysResolved = true;
                    toRemove--;
                }
            }
        }
    }

}

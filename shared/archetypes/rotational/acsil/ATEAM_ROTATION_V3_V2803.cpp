#include "sierrachart.h"
#include <cstdio>

SCDLLName("ATEAM_ROTATION_V3_V2803")

static void WriteCSV(SCStudyInterfaceRef sc,
    int*        pHeaderWritten,
    const char* Event,
    const char* Side,
    double      Price,
    double      AvgEntryPrice,
    int         PosQty,
    int         AddQty,
    int         Level,
    double      PnlTicks,
    double      StepDist,
    int         MaxLevels,
    int         MaxContractSize)
{
    SCString FilePath;
    FilePath.Format("%s\\ATEAM_ROTATION_V3_V2803_log.csv", sc.DataFilesFolder().GetChars());

    int NeedHeader = 0;
    if (*pHeaderWritten == 0)
    {
        FILE* fCheck = fopen(FilePath.GetChars(), "r");
        if (fCheck == NULL)
        {
            NeedHeader = 1;
        }
        else
        {
            fseek(fCheck, 0, SEEK_END);
            if (ftell(fCheck) == 0)
                NeedHeader = 1;
            else
                *pHeaderWritten = 1;
            fclose(fCheck);
        }
    }

    FILE* f = fopen(FilePath.GetChars(), "a");
    if (f == NULL)
        return;

    if (NeedHeader)
    {
        fprintf(f,
            "DateTime,Symbol,Event,Side,Price,AvgEntryPrice,PosQty,AddQty,"
            "Level,PnlTicks,StepDist,MaxLevels,MaxContractSize\n");
        *pHeaderWritten = 1;
    }

    int Year, Month, Day, Hour, Minute, Second;
    sc.CurrentSystemDateTime.GetDateTimeYMDHMS(Year, Month, Day,
                                                Hour, Minute, Second);

    fprintf(f,
        "%04d-%02d-%02d %02d:%02d:%02d,%s,%s,%s,"
        "%.2f,%.2f,%d,%d,"
        "%d,%.1f,%.2f,%d,%d\n",
        Year, Month, Day, Hour, Minute, Second,
        sc.GetChartSymbol(sc.ChartNumber).GetChars(),
        Event, Side,
        Price, AvgEntryPrice, PosQty, AddQty,
        Level, PnlTicks, StepDist, MaxLevels, MaxContractSize);

    fclose(f);
}

SCSFExport scsf_ATEAM_ROTATION_V3_V2803(SCStudyInterfaceRef sc)
{
    SCSubgraphRef sg_FilterBG = sc.Subgraph[0];

    if (sc.SetDefaults)
    {
        sc.GraphName = "ATEAM Rotation V3";
        sc.AutoLoop = 1;
        sc.UpdateAlways = 1;
        sc.GraphRegion = 0;

        sc.AllowMultipleEntriesInSameDirection = 1;
        sc.MaximumPositionAllowed = 100;
        sc.SupportReversals = 0;
        sc.SendOrdersToTradeService = 0;
        sc.AllowOppositeEntryWithOpposingPositionOrOrders = 1;
        sc.SupportAttachedOrdersForTrading = 0;
        sc.CancelAllOrdersOnEntriesAndReversals = 0;
        sc.AllowEntryWithWorkingOrders = 1;
        sc.CancelAllWorkingOrdersOnExit = 1;
        sc.AllowOnlyOneTradePerBar = 0;
        sc.MaintainTradeStatisticsAndTradesData = 1;

        // Background highlight subgraph
        sg_FilterBG.Name = "Speed Filter BG";
        sg_FilterBG.DrawStyle = DRAWSTYLE_BACKGROUND;
        sg_FilterBG.PrimaryColor = RGB(80, 80, 0);       // green tint = trades ON
        sg_FilterBG.SecondaryColor = RGB(80, 0, 0);      // red tint = trades OFF
        sg_FilterBG.SecondaryColorUsed = 1;
        sg_FilterBG.DrawZeros = 0;

        sc.Input[0].Name = "Step Dist (pts)";
        sc.Input[0].SetFloat(2.0f);

        sc.Input[1].Name = "Initial Qty";
        sc.Input[1].SetInt(1);

        sc.Input[2].Name = "Max Martingale Levels (1=1, 2=1,2, 3=1,2,4, 4=1,2,4,8)";
        sc.Input[2].SetInt(4);

        sc.Input[3].Name = "Max Contract Size (resets to Initial after hitting this)";
        sc.Input[3].SetInt(8);

        sc.Input[4].Name = "Enable";
        sc.Input[4].SetYesNo(1);

        sc.Input[5].Name = "CSV Log";
        sc.Input[5].SetYesNo(1);

        sc.Input[6].Name = "Hard Stop (ticks, 0=disabled)";
        sc.Input[6].SetFloat(0.0f);

        sc.Input[7].Name = "Max Direction Fades (0=unlimited)";
        sc.Input[7].SetInt(0);

        sc.Input[8].Name = "Enable Speed Filter";
        sc.Input[8].SetYesNo(0);

        sc.Input[9].Name = "SpeedRead Study Ref";
        sc.Input[9].SetStudySubgraphValues(0, 0);

        sc.Input[10].Name = "Speed Slow Threshold (trades ON below)";
        sc.Input[10].SetFloat(30.0f);

        sc.Input[11].Name = "Speed Fast Threshold (stop out above)";
        sc.Input[11].SetFloat(70.0f);

        return;
    }

    sc.SendOrdersToTradeService = 0;

    if (!sc.Input[4].GetYesNo())
        return;

    const double StepDist        = sc.Input[0].GetFloat();
    const int    InitialQty      = sc.Input[1].GetInt();
    const int    MaxLevels       = sc.Input[2].GetInt();
    const int    MaxContractSize = sc.Input[3].GetInt();
    const int    CSVEnabled      = sc.Input[5].GetYesNo();
    const double HardStop        = sc.Input[6].GetFloat();
    const int    MaxFades        = sc.Input[7].GetInt();
    const int    SpeedFilterEnabled = sc.Input[8].GetYesNo();
    const float  SpeedSlowThresh   = sc.Input[10].GetFloat();
    const float  SpeedFastThresh   = sc.Input[11].GetFloat();

    // persistent state
    double& AnchorPrice    = sc.GetPersistentDouble(0);
    double& WatchPrice     = sc.GetPersistentDouble(1);
    double& WatchHigh      = sc.GetPersistentDouble(2);
    double& WatchLow       = sc.GetPersistentDouble(3);
    int&    Direction      = sc.GetPersistentInt(0);   // 1=long, -1=short
    int&    Level          = sc.GetPersistentInt(1);   // 0..MaxLevels-1
    int&    OrderPending   = sc.GetPersistentInt(2);   // 1=waiting for fill
    int&    FlattenPending = sc.GetPersistentInt(3);   // 1=waiting for flatten
    int&    CSVHeader      = sc.GetPersistentInt(4);   // CSV header written flag
    int&    FadeCountLong  = sc.GetPersistentInt(5);   // consecutive long entries
    int&    FadeCountShort = sc.GetPersistentInt(6);   // consecutive short entries
    int&    SpeedFilterOff = sc.GetPersistentInt(7);   // 0=trades allowed, 1=disabled (fast tape)

    // Read SpeedRead study data (only if filter enabled)
    float SpeedVal = 0.0f;
    if (SpeedFilterEnabled)
    {
        SCFloatArray SpeedData;
        sc.GetStudyArrayUsingID(sc.Input[9].GetStudyID(), sc.Input[9].GetSubgraphIndex(), SpeedData);
        SpeedVal = (SpeedData.GetArraySize() > sc.Index) ? SpeedData[sc.Index] : 0.0f;

        // Background highlight: user-picked color only on bars where speed is below slow threshold
        if (SpeedVal > 0.0f && SpeedVal <= SpeedSlowThresh)
        {
            sg_FilterBG[sc.Index] = 1.0f;
            sg_FilterBG.DataColor[sc.Index] = sg_FilterBG.PrimaryColor;
        }
        else
        {
            sg_FilterBG[sc.Index] = 0.0f;
        }
    }
    else
    {
        sg_FilterBG[sc.Index] = 0.0f;
    }

    // Only run trade logic on last bar
    if (sc.Index != sc.ArraySize - 1)
        return;

    s_SCPositionData Pos;
    sc.GetTradePosition(Pos);
    int    PosQty = Pos.PositionQuantity;
    double Price  = sc.Close[sc.Index];

    auto Market = [&](int side, int qty) -> bool
    {
        s_SCNewOrder O;
        O.OrderQuantity = qty;
        O.OrderType     = SCT_ORDERTYPE_MARKET;
        O.TimeInForce   = SCT_TIF_GTC;
        int r = side > 0 ? sc.BuyEntry(O) : sc.SellEntry(O);
        return r > 0;
    };

    // Helper: check if direction is blocked by fade filter
    auto FadeBlocked = [&](int dir) -> bool
    {
        if (MaxFades <= 0) return false;
        if (dir == 1  && FadeCountLong  >= MaxFades) return true;
        if (dir == -1 && FadeCountShort >= MaxFades) return true;
        return false;
    };

    // Helper: update fade counters after entering a direction
    auto UpdateFadeCount = [&](int dir)
    {
        if (dir == 1)
        {
            FadeCountLong++;
            FadeCountShort = 0;
        }
        else
        {
            FadeCountShort++;
            FadeCountLong = 0;
        }
    };

    // Helper: reset all state to watching mode
    auto ResetToWatching = [&]()
    {
        AnchorPrice    = 0.0;
        Direction      = 0;
        Level          = 0;
        OrderPending   = 0;
        FlattenPending = 0;
        WatchPrice     = 0.0;
        WatchHigh      = 0.0;
        WatchLow       = 0.0;
    };

    // DEBUG
    {
        SCString msg;
        msg.Format("Dir:%d Level:%d Pos:%d Anchor:%.2f Price:%.2f Pend:%d Flat:%d FadesL:%d FadesS:%d Speed:%.1f FilterOff:%d",
                   Direction, Level, PosQty, AnchorPrice, Price, OrderPending, FlattenPending,
                   FadeCountLong, FadeCountShort, SpeedVal, SpeedFilterOff);
        sc.AddMessageToTradeServiceLog(msg, 0);
    }

    // HARD STOP CHECK: runs FIRST — always active regardless of speed filter
    if (PosQty != 0 && HardStop > 0.0 && !FlattenPending)
    {
        double AvgEntry = Pos.AveragePrice;
        double UnrealizedPts = (PosQty > 0)
            ? (AvgEntry - Price)
            : (Price - AvgEntry);
        double UnrealizedTicks = UnrealizedPts / sc.TickSize;

        if (UnrealizedTicks >= HardStop)
        {
            SCString msg;
            msg.Format("*** HARD STOP HIT (%.0f ticks against) - FLATTENING ***", UnrealizedTicks);
            sc.AddMessageToTradeServiceLog(msg, 1);

            if (CSVEnabled)
            {
                WriteCSV(sc, &CSVHeader, "HARD_STOP",
                    Direction == 1 ? "LONG" : "SHORT",
                    Price, AvgEntry, PosQty, 0, Level, -UnrealizedTicks,
                    StepDist, MaxLevels, MaxContractSize);
            }

            sc.FlattenAndCancelAllOrders();
            ResetToWatching();
            return;
        }
    }

    // SPEED FILTER: hysteresis — off when fast, back on when slow
    if (SpeedFilterEnabled)
    {
        if (SpeedFilterOff == 0 && SpeedVal >= SpeedFastThresh)
        {
            SpeedFilterOff = 1;
            sc.AddMessageToTradeServiceLog("*** SPEED FILTER OFF - FAST TAPE - STOPPING ***", 1);

            if (CSVEnabled)
                WriteCSV(sc, &CSVHeader, "SPEED_FILTER_OFF", "NONE",
                    Price, 0.0, PosQty, 0, Level, 0.0,
                    StepDist, MaxLevels, MaxContractSize);

            // If in a position, flatten and reset
            if (PosQty != 0)
            {
                sc.FlattenAndCancelAllOrders();
                ResetToWatching();
            }
            else
            {
                ResetToWatching();
            }
            return;
        }

        if (SpeedFilterOff == 1)
        {
            if (SpeedVal <= SpeedSlowThresh)
            {
                SpeedFilterOff = 0;
                sc.AddMessageToTradeServiceLog("*** SPEED FILTER ON - SLOW TAPE - TRADING RESUMED ***", 1);

                if (CSVEnabled)
                    WriteCSV(sc, &CSVHeader, "SPEED_FILTER_ON", "NONE",
                        Price, 0.0, 0, 0, 0, 0.0,
                        StepDist, MaxLevels, MaxContractSize);

                // Reset to watching so it can find a new entry
                ResetToWatching();
                // Fall through to normal logic
            }
            else
            {
                // Still fast — if somehow still in a position, flatten
                if (PosQty != 0)
                {
                    sc.FlattenAndCancelAllOrders();
                    ResetToWatching();
                }
                return;  // no trading
            }
        }
    }

    // Handle flatten pending: wait until position is actually flat
    if (FlattenPending)
    {
        if (PosQty != 0)
            return;  // still waiting for flatten to complete

        // Flatten complete — now enter opposite direction
        FlattenPending = 0;
        int NewDir = -Direction;

        // Check fade filter before entering opposite direction
        if (FadeBlocked(NewDir))
        {
            SCString msg;
            msg.Format("*** FADE LIMIT REACHED (%s blocked) - GOING TO WATCH ***",
                       NewDir == 1 ? "LONG" : "SHORT");
            sc.AddMessageToTradeServiceLog(msg, 1);

            if (CSVEnabled)
                WriteCSV(sc, &CSVHeader, "FADE_BLOCKED",
                    NewDir == 1 ? "LONG" : "SHORT",
                    Price, 0.0, 0, 0, Level, 0.0,
                    StepDist, MaxLevels, MaxContractSize);

            ResetToWatching();
            return;
        }

        if (Market(NewDir, InitialQty))
        {
            Direction    = NewDir;
            AnchorPrice  = Price;
            Level        = 0;
            OrderPending = 1;
            UpdateFadeCount(NewDir);
            sc.AddMessageToTradeServiceLog("*** REVERSAL ENTRY SENT ***", 1);

            if (CSVEnabled)
                WriteCSV(sc, &CSVHeader, "REVERSAL_ENTRY",
                    NewDir == 1 ? "LONG" : "SHORT",
                    Price, Price, InitialQty, InitialQty, 0, 0.0,
                    StepDist, MaxLevels, MaxContractSize);
        }
        return;
    }

    // Handle order pending: wait until position reflects our order
    if (OrderPending)
    {
        if (PosQty == 0)
            return;  // still waiting for fill
        OrderPending = 0;  // filled, resume normal logic
    }

    // 1) Seed: track running high/low, enter on PULLBACK of StepDist from extreme
    if (PosQty == 0 && AnchorPrice == 0.0)
    {
        // Phase A: start watching — record reference price, no trade yet
        if (WatchPrice == 0.0)
        {
            WatchPrice = Price;
            WatchHigh  = Price;
            WatchLow   = Price;
            sc.AddMessageToTradeServiceLog("WATCHING: recording reference price", 1);
            return;
        }

        // Update running high/low
        if (Price > WatchHigh) WatchHigh = Price;
        if (Price < WatchLow)  WatchLow  = Price;

        // Phase B: wait for pullback from extreme to decide direction
        // LONG  = price made a high, then pulled back StepDist down from it
        // SHORT = price made a low,  then pulled back StepDist up from it
        double pullFromHigh = WatchHigh - Price;
        double pullFromLow  = Price - WatchLow;

        int SeedDir = 0;
        if (pullFromHigh >= StepDist && pullFromLow >= StepDist)
        {
            // Both qualify — pick the larger pullback
            SeedDir = (pullFromHigh >= pullFromLow) ? 1 : -1;
        }
        else if (pullFromHigh >= StepDist)
            SeedDir = 1;   // long — pullback from high
        else if (pullFromLow >= StepDist)
            SeedDir = -1;  // short — pullback from low
        else
            return;  // not enough pullback yet

        // Check fade filter before seeding
        if (FadeBlocked(SeedDir))
        {
            SCString msg;
            msg.Format("*** FADE LIMIT - %s BLOCKED, TRYING OPPOSITE ***",
                       SeedDir == 1 ? "LONG" : "SHORT");
            sc.AddMessageToTradeServiceLog(msg, 1);

            // Try the other direction if it also moved enough
            // Otherwise just keep watching
            SeedDir = -SeedDir;
            bool otherMoved = (SeedDir == 1)
                ? (pullFromHigh >= StepDist)
                : (pullFromLow >= StepDist);

            if (!otherMoved || FadeBlocked(SeedDir))
                return;  // neither direction available, keep watching
        }

        if (Market(SeedDir, InitialQty))
        {
            Direction    = SeedDir;
            Level        = 0;
            AnchorPrice  = Price;
            WatchPrice   = 0.0;
            OrderPending = 1;
            UpdateFadeCount(SeedDir);

            const char* Side = SeedDir == 1 ? "LONG" : "SHORT";
            SCString msg;
            msg.Format("SEED: %s base size", Side);
            sc.AddMessageToTradeServiceLog(msg, 1);

            if (CSVEnabled)
                WriteCSV(sc, &CSVHeader, "SEED", Side,
                    Price, Price, InitialQty, InitialQty, 0, 0.0,
                    StepDist, MaxLevels, MaxContractSize);
        }
        return;
    }

    // Reset state if flat unexpectedly (and no orders pending)
    if (PosQty == 0)
    {
        ResetToWatching();
        return;
    }

    int PosSide = (PosQty > 0 ? 1 : -1);

    // resync direction if needed
    if (Direction == 0 || Direction != PosSide)
    {
        Direction   = PosSide;
        AnchorPrice = Price;
        Level       = 0;
    }

    double upMove   = Price - AnchorPrice;
    double downMove = AnchorPrice - Price;

    bool inFavor = (Direction == 1 ? upMove >= StepDist : downMove >= StepDist);
    bool against = (Direction == 1 ? downMove >= StepDist : upMove >= StepDist);

    // 2) REVERSAL: price moved StepDist in favor -> flatten, then flip
    if (inFavor)
    {
        double AvgEntry = Pos.AveragePrice;
        double PnlTicks = (Direction == 1)
            ? (Price - AvgEntry) / sc.TickSize
            : (AvgEntry - Price) / sc.TickSize;

        sc.AddMessageToTradeServiceLog("*** REVERSAL - FLATTENING ***", 1);

        if (CSVEnabled)
            WriteCSV(sc, &CSVHeader, "REVERSAL",
                Direction == 1 ? "LONG" : "SHORT",
                Price, AvgEntry, PosQty, 0, Level, PnlTicks,
                StepDist, MaxLevels, MaxContractSize);

        sc.FlattenAndCancelAllOrders();
        FlattenPending = 1;
        return;
    }

    // 3) MARTINGALE: price moved StepDist against -> add next size
    if (against)
    {
        int useLevel = Level;
        if (useLevel >= MaxLevels)
            useLevel = 0;

        int addQty = (int)(InitialQty * pow(2.0, useLevel) + 0.5);
        int absPos = abs(PosQty);

        // Check if total position would exceed max contract size
        if (absPos + addQty > MaxContractSize)
        {
            // Try to fill remaining room up to max
            int room = MaxContractSize - absPos;
            if (room <= 0)
            {
                sc.AddMessageToTradeServiceLog("*** MAX SIZE HIT - CANNOT ADD ***", 1);
                return;
            }
            addQty = room;
            Level = 0;

            SCString msg2;
            msg2.Format("*** MAX SIZE CAP - ADDING %d TO FILL TO %d ***", addQty, MaxContractSize);
            sc.AddMessageToTradeServiceLog(msg2, 1);
        }

        SCString msg;
        msg.Format("*** MARTINGALE ADD qty=%d (Level=%d) ***", addQty, useLevel);
        sc.AddMessageToTradeServiceLog(msg, 1);

        if (Market(Direction, addQty))
        {
            Level++;
            if (Level >= MaxLevels)
                Level = 0;
            AnchorPrice  = Price;
            OrderPending = 1;

            if (CSVEnabled)
                WriteCSV(sc, &CSVHeader, "ADD",
                    Direction == 1 ? "LONG" : "SHORT",
                    Price, Pos.AveragePrice,
                    PosQty + (Direction > 0 ? addQty : -addQty),
                    addQty, Level, 0.0,
                    StepDist, MaxLevels, MaxContractSize);
        }
        return;
    }
}

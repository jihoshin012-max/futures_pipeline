#include "sierrachart.h"
#include <cstdio>

SCDLLName("ATEAM_ROTATION_V1_OG")

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
    FilePath.Format("%s\\ATEAM_ROTATION_V1_OG_log.csv", sc.DataFilesFolder().GetChars());

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

SCSFExport scsf_ATEAM_ROTATION_V1_OG(SCStudyInterfaceRef sc)
{
    if (sc.SetDefaults)
    {
        sc.GraphName = "ATEAM Rotation V1 OG";
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

        return;
    }

    sc.SendOrdersToTradeService = 0;

    if (!sc.Input[4].GetYesNo())
        return;

    // Only run on last bar
    if (sc.Index != sc.ArraySize - 1)
        return;

    const double StepDist        = sc.Input[0].GetFloat();
    const int    InitialQty      = sc.Input[1].GetInt();
    const int    MaxLevels       = sc.Input[2].GetInt();
    const int    MaxContractSize = sc.Input[3].GetInt();
    const int    CSVEnabled      = sc.Input[5].GetYesNo();

    // persistent state
    double& AnchorPrice   = sc.GetPersistentDouble(0);
    int&    Direction     = sc.GetPersistentInt(0);   // 1=long, -1=short
    int&    Level         = sc.GetPersistentInt(1);   // 0..MaxLevels-1
    int&    OrderPending  = sc.GetPersistentInt(2);   // 1=waiting for fill
    int&    FlattenPending = sc.GetPersistentInt(3);  // 1=waiting for flatten
    int&    CSVHeader     = sc.GetPersistentInt(4);   // CSV header written flag

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

    // DEBUG
    {
        SCString msg;
        msg.Format("Dir:%d Level:%d Pos:%d Anchor:%.2f Price:%.2f Pend:%d Flat:%d",
                   Direction, Level, PosQty, AnchorPrice, Price, OrderPending, FlattenPending);
        sc.AddMessageToTradeServiceLog(msg, 0);
    }

    // Handle flatten pending: wait until position is actually flat
    if (FlattenPending)
    {
        if (PosQty != 0)
            return;  // still waiting for flatten to complete

        // Flatten complete — now enter opposite direction
        FlattenPending = 0;
        int NewDir = -Direction;
        if (Market(NewDir, InitialQty))
        {
            Direction    = NewDir;
            AnchorPrice  = Price;
            Level        = 0;
            OrderPending = 1;
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

    // 1) Seed if flat: start long with InitialQty
    if (PosQty == 0 && AnchorPrice == 0.0)
    {
        if (Market(1, InitialQty))
        {
            Direction    = 1;
            Level        = 0;
            AnchorPrice  = Price;
            OrderPending = 1;
            sc.AddMessageToTradeServiceLog("SEED: LONG base size", 1);

            if (CSVEnabled)
                WriteCSV(sc, &CSVHeader, "SEED", "LONG",
                    Price, Price, InitialQty, InitialQty, 0, 0.0,
                    StepDist, MaxLevels, MaxContractSize);
        }
        return;
    }

    // Reset state if flat unexpectedly (and no orders pending)
    if (PosQty == 0)
    {
        AnchorPrice    = 0.0;
        Direction      = 0;
        Level          = 0;
        OrderPending   = 0;
        FlattenPending = 0;
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

        if (addQty > MaxContractSize)
        {
            addQty = InitialQty;
            Level = 0;
            sc.AddMessageToTradeServiceLog("*** MAX SIZE HIT - RESETTING TO INITIAL QTY ***", 1);
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
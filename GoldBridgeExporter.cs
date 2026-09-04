#region Using declarations
using System;
using System.ComponentModel.DataAnnotations;
using System.Globalization;
using System.IO;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.NinjaScript;
using NinjaTrader.NinjaScript.Indicators;
#endregion

// ============================================================================
//  GoldBridgeExporter  (NinjaTrader 8 indicator)
// ----------------------------------------------------------------------------
//  Streams live market data (trades, bid/ask quotes, and order-book depth)
//  from NinjaTrader to a CSV file, so the Python robot
//  (gold_robot_ntbridge.py) can read it.
//
//  WHY: your Rithmic trial account works inside NinjaTrader (NinjaTrader's
//  application is authorized by Rithmic), but custom applications are blocked
//  by Rithmic's permission policy. This bridge uses NinjaTrader's authorized
//  connection as the data source.
//
//  INSTALL:  NinjaScript Editor -> right-click "Indicators" -> New Indicator ->
//            name it GoldBridgeExporter -> Generate -> select ALL generated
//            code, delete it, paste THIS ENTIRE FILE -> press F5 to compile.
//
//  USE:      Open a chart of GC (front month, any timeframe), add the
//            "GoldBridgeExporter" indicator to it, and keep the chart open.
//            Data is written to  C:\NinjaBridge\ticks.csv
//
//  NOTES:    - File is opened/closed per write, so the file is never locked
//              by NinjaTrader and survives restarts.
//            - Numbers are written with invariant culture (dots, not commas),
//              so it works on Hungarian Windows too.
// ============================================================================

namespace NinjaTrader.NinjaScript.Indicators
{
    public class GoldBridgeExporter : Indicator
    {
        private string filePath;

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Description = "Exports live market data (trades, quotes, depth) to a CSV file for the Python robot.";
                Name = "GoldBridgeExporter";
                Calculate = Calculate.OnEachTick;      // required: receive every tick event
                IsOverlay = true;
                DrawOnPricePanel = true;
                OutputFolder = @"C:\NinjaBridge";
                ExportDepth = true;
            }
            else if (State == State.Configure)
            {
                try
                {
                    Directory.CreateDirectory(OutputFolder);
                    filePath = Path.Combine(OutputFolder, "ticks.csv");
                    if (!File.Exists(filePath))
                        File.AppendAllText(filePath,
                            "time,event,price,size,level,operation,instrument" + Environment.NewLine);
                    Print("GoldBridgeExporter: writing to " + filePath);
                }
                catch (Exception ex)
                {
                    filePath = null;
                    Print("GoldBridgeExporter: CANNOT create output file: " + ex.Message);
                }
            }
        }

        protected override void OnBarUpdate()
        {
            // Not used - we only care about tick-level events below.
        }

        // Level 1: every trade / best bid / best ask event
        protected override void OnMarketData(MarketDataEventArgs e)
        {
            if (filePath == null)
                return;
            // MarketDataType.ToString() gives "Last", "Bid", "Ask" (and a few
            // exotic types the Python side simply ignores).
            Write(e.Time, e.MarketDataType.ToString(), e.Price, e.Volume, -1, "", Instrument.FullName);
        }

        // Level 2: order book depth (DOM) updates - if the feed provides them
        protected override void OnMarketDepth(MarketDepthEventArgs e)
        {
            // e.IsReset events are UI-reconnect resets, not real depth data - skip them
            if (filePath == null || !ExportDepth || e.IsReset)
                return;
            // e.g. event "DepthBid" / "DepthAsk", operation "Add"/"Update"/"Remove"
            Write(e.Time, "Depth" + e.MarketDataType.ToString(), e.Price, e.Volume, e.Position,
                  e.Operation.ToString(), Instrument.FullName);
        }

        private void Write(DateTime t, string ev, double price, long size, int level, string op, string instrument)
        {
            try
            {
                // InvariantCulture -> always "4102.25", never "4102,25"
                string line = string.Format(CultureInfo.InvariantCulture,
                    "{0:yyyy-MM-ddTHH:mm:ss.fff},{1},{2:R},{3},{4},{5},{6}{7}",
                    t, ev, price, size, level, op, instrument, Environment.NewLine);
                File.AppendAllText(filePath, line);
            }
            catch (Exception ex)
            {
                Print("GoldBridgeExporter write error: " + ex.Message);
            }
        }

        #region Properties
        [NinjaScriptProperty]
        [Display(Name = "Output folder", GroupName = "Bridge settings", Order = 1)]
        public string OutputFolder { get; set; }

        [NinjaScriptProperty]
        [Display(Name = "Export market depth (L2)", GroupName = "Bridge settings", Order = 2)]
        public bool ExportDepth { get; set; }
        #endregion
    }
}


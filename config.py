"""
Configuration for the UK relative-value screener.

Everything the screener needs to know about *what* to compare lives here:
sector groupings, tickers, which metrics apply to each sector, how they are
weighted, and global settings. The screener code reads this file and never
hard-codes a ticker or metric choice.

The universe is built from the FTSE 350 as of October 2026, excluding
investment trusts, closed-end funds and pre-revenue companies, since
earnings-based valuation doesn't apply to them. Mergers, renames and
delistings happen often: run check_tickers.py to find tickers that no longer
return data. A ticker that fails during a full run is also listed in the
HTML report rather than stopping the run.
"""

# ---------------------------------------------------------------------------
# Global settings
# ---------------------------------------------------------------------------

SETTINGS = {
    # Days between a fiscal period end and the date we assume its results were
    # public. UK companies have four months to publish annual reports, so 120
    # days is a conservative point-in-time assumption.
    "reporting_lag_days": 120,

    # How far back to compute peer-relative valuation history. yfinance only
    # serves about four years of annual statements, so going further adds
    # nothing for the fundamental metrics.
    "history_years": 4,

    # Evaluation dates for the history are taken at this frequency.
    # "QE" = quarter end. Note: the points are not independent, since the
    # underlying fundamentals only change once a year.
    "history_frequency": "QE",

    # Minimum historical observations before a history score is produced.
    "min_history_points": 4,

    # Years of price and dividend history for the dividend-yield percentile.
    "dividend_history_years": 15,

    # A single dividend payment larger than this multiple of the largest of
    # the previous six payments is treated as a special dividend and excluded
    # from the trailing yield.
    "special_dividend_multiple": 2.5,

    # Weights for the composite score. Components that are missing for a
    # company are dropped and the remaining weights are renormalised.
    "composite_weights": {
        "peer_value": 0.45,     # cheap versus sector peers today
        "history_value": 0.25,  # cheap versus its own peer-relative history
        "dividend_value": 0.10, # trailing yield versus its own long history
        "quality": 0.20,        # profitability and balance-sheet strength
    },

    # A company scoring at least this on peer value but at most this on
    # quality is flagged as a possible value trap.
    "value_trap_value_min": 70,
    "value_trap_quality_max": 35,

    # Number of companies in the cross-sector summary table.
    "top_n_overall": 25,

    # Pause between ticker downloads (seconds) to stay polite to Yahoo.
    "request_pause_seconds": 0.4,

    # Reports are written to this folder, created next to the code if it
    # doesn't exist. {date} is replaced with the run date (YYYY-MM-DD), so
    # reports sort in date order; a second run on the same day overwrites
    # that day's report. Demo runs get "_demo" added to the name.
    "output_dir": "output",
    " filename": "uk_value_screen_{date}.html",
}


# ---------------------------------------------------------------------------
# Metric definitions
# ---------------------------------------------------------------------------
# kind:
#   "valuation" - a price multiple. Scored on its inverse (a yield), so that
#                 higher always means cheaper and loss-makers rank as
#                 expensive instead of producing meaningless negative P/Es.
#                 yield_label is the name shown when the report is switched
#                 to yield view.
#   "yield"     - already a yield; higher means cheaper.
#   "quality"   - profitability, cash or balance-sheet measure.
# higher_is_better applies to quality metrics only.
# snapshot_only: the value comes from Yahoo's current snapshot and has no
#                history, so it counts towards the peer score but not the
#                own-history score.
# fmt is the display format used in the HTML report.

METRICS = {
    # Valuation multiples
    "pe":        {"label": "P/E", "yield_label": "Earnings yield",
                  "kind": "valuation", "fmt": "{:.1f}x"},
    "pe_avg":    {"label": "P/E (avg. earnings)", "yield_label": "Avg. earnings yield",
                  "kind": "valuation", "fmt": "{:.1f}x"},
    "fwd_pe":    {"label": "Forward P/E", "yield_label": "Fwd. earnings yield",
                  "kind": "valuation", "fmt": "{:.1f}x", "snapshot_only": True},
    "pb":        {"label": "P/B", "yield_label": "Book yield",
                  "kind": "valuation", "fmt": "{:.2f}x"},
    "ptbv":      {"label": "P/TBV", "yield_label": "Tangible book yield",
                  "kind": "valuation", "fmt": "{:.2f}x"},
    "p_ocf":     {"label": "P/OCF", "yield_label": "Op. cash flow yield",
                  "kind": "valuation", "fmt": "{:.1f}x"},
    "ev_ebitda": {"label": "EV/EBITDA", "yield_label": "EBITDA yield",
                  "kind": "valuation", "fmt": "{:.1f}x"},
    "ev_ebit":   {"label": "EV/EBIT", "yield_label": "EBIT yield",
                  "kind": "valuation", "fmt": "{:.1f}x"},
    "ev_sales":  {"label": "EV/Sales", "yield_label": "Sales yield",
                  "kind": "valuation", "fmt": "{:.2f}x"},
    "ev_gp":     {"label": "EV/Gross profit", "yield_label": "Gross profit yield",
                  "kind": "valuation", "fmt": "{:.1f}x"},

    # Yields
    "fcf_yield":         {"label": "FCF yield", "kind": "yield", "fmt": "{:.1%}"},
    "ufcf_yield":        {"label": "Unlevered FCF yield", "kind": "yield", "fmt": "{:.1%}"},
    "div_yield":         {"label": "Div. yield", "kind": "yield", "fmt": "{:.1%}"},
    "shareholder_yield": {"label": "Shareholder yield", "kind": "yield", "fmt": "{:.1%}"},

    # Quality: returns
    "roe":   {"label": "ROE",  "kind": "quality", "higher_is_better": True, "fmt": "{:.1%}"},
    "rote":  {"label": "ROTE", "kind": "quality", "higher_is_better": True, "fmt": "{:.1%}"},
    "roa":   {"label": "ROA",  "kind": "quality", "higher_is_better": True, "fmt": "{:.2%}"},
    "roic":  {"label": "ROIC", "kind": "quality", "higher_is_better": True, "fmt": "{:.1%}"},
    # Quality: margins and growth
    "gross_margin":   {"label": "Gross margin",   "kind": "quality", "higher_is_better": True, "fmt": "{:.1%}"},
    "op_margin":      {"label": "Op. margin",     "kind": "quality", "higher_is_better": True, "fmt": "{:.1%}"},
    "margin_trend":   {"label": "Margin trend",   "kind": "quality", "higher_is_better": True, "fmt": "{:+.1%}"},
    "revenue_growth": {"label": "Revenue growth", "kind": "quality", "higher_is_better": True, "fmt": "{:+.1%}"},
    # Quality: cash and balance sheet
    "cash_conversion": {"label": "Cash conversion", "kind": "quality", "higher_is_better": True,  "fmt": "{:.0%}"},
    "net_debt_ebitda": {"label": "Net debt/EBITDA", "kind": "quality", "higher_is_better": False, "fmt": "{:.1f}x"},
    "interest_cover":  {"label": "Interest cover",  "kind": "quality", "higher_is_better": True,  "fmt": "{:.1f}x"},
    "dividend_cover":  {"label": "Dividend cover",  "kind": "quality", "higher_is_better": True,  "fmt": "{:.1f}x"},
    "share_change":    {"label": "Share count change", "kind": "quality", "higher_is_better": False, "fmt": "{:+.1%}"},
    "piotroski":       {"label": "Piotroski F-score",  "kind": "quality", "higher_is_better": True,  "fmt": "{:.0f}/9"},
}


# ---------------------------------------------------------------------------
# Sector definitions
# ---------------------------------------------------------------------------
# Each sector lists:
#   tickers           - {Yahoo ticker: display name}
#   valuation         - {metric: weight} used for the peer and history scores
#   quality           - {metric: weight} used for the quality score
#   regression        - (x, y) for the "multiple versus fundamentals" chart:
#                       y is a valuation multiple, x the fundamental that
#                       should justify it. None to skip.
#   notes             - shown in the report, to explain metric choices.
# Any metric in METRICS can be used in any sector; weights need not sum to 1.

SECTORS = {
    # ----- Financials -------------------------------------------------------
    "banks": {
        "name": "Banks",
        "notes": "EV-based multiples are meaningless for banks, since debt is "
                 "their raw material. Valuation is tangible-book-based, judged "
                 "against ROTE. Shareholder yield captures the large buybacks "
                 "UK banks now run alongside dividends. Lion Finance and TBC "
                 "operate mainly in Georgia.",
        "tickers": {
            "HSBA.L": "HSBC",
            "LLOY.L": "Lloyds Banking Group",
            "BARC.L": "Barclays",
            "NWG.L":  "NatWest Group",
            "STAN.L": "Standard Chartered",
            "BGEO.L": "Lion Finance Group",
            "TBCG.L": "TBC Bank",
            "INVP.L": "Investec",
            "OSB.L":  "OSB Group",
            "PAG.L":  "Paragon Banking",
            "SHAW.L": "Shawbrook",
            "CBG.L":  "Close Brothers",
            "MTRO.L": "Metro Bank",
        },
        "valuation": {"ptbv": 0.4, "pe": 0.3, "shareholder_yield": 0.3},
        "quality": {"rote": 0.5, "roa": 0.3, "dividend_cover": 0.2},
        "regression": ("rote", "ptbv"),
    },

    "insurance": {
        "name": "Insurance",
        "notes": "Book-based valuation for the same reason as banks. Life and "
                 "non-life insurers are grouped together; consider splitting "
                 "them if the peer group looks mismatched.",
        "tickers": {
            "LGEN.L": "Legal & General",
            "AV.L":   "Aviva",
            "PRU.L":  "Prudential",
            "SDLF.L": "Standard Life",
            "ADM.L":  "Admiral",
            "HSX.L":  "Hiscox",
            "LRE.L":  "Lancashire",
            "CSN.L":  "Chesnara",
        },
        "valuation": {"pb": 0.4, "pe": 0.3, "shareholder_yield": 0.3},
        "quality": {"roe": 0.6, "dividend_cover": 0.4},
        "regression": ("roe", "pb"),
    },

    "financial_services": {
        "name": "Asset managers, platforms & brokers",
        "notes": "Asset-light businesses whose balance sheets often hold client "
                 "money, so EV-based multiples are unreliable. Valued on "
                 "earnings and cash returned. Earnings move with markets, so "
                 "forward P/E is included. 3i is valued by the market mainly "
                 "on its net asset value.",
        "tickers": {
            "LSEG.L": "London Stock Exchange Group",
            "III.L":  "3i Group",
            "ABDN.L": "Aberdeen Group",
            "MNG.L":  "M&G",
            "STJ.L":  "St. James's Place",
            "ICG.L":  "ICG",
            "IGG.L":  "IG Group",
            "EMG.L":  "Man Group",
            "AJB.L":  "AJ Bell",
            "IHP.L":  "IntegraFin",
            "QLT.L":  "Quilter",
            "RAT.L":  "Rathbones",
            "JUP.L":  "Jupiter Fund Management",
            "ASHM.L": "Ashmore Group",
            "N91.L":  "Ninety One",
            "BPT.L":  "Bridgepoint Group",
            "FSG.L":  "Foresight Group",
            "PLUS.L": "Plus500",
            "CMCX.L": "CMC Markets",
            "TCAP.L": "TP ICAP",
            "POLN.L": "Pollen Street Group",
            "FCH.L":  "Funding Circle",
            "EWG.L":  "Eurowag",
        },
        "valuation": {"pe": 0.4, "fwd_pe": 0.3, "shareholder_yield": 0.3},
        "quality": {"roe": 0.4, "op_margin": 0.3, "dividend_cover": 0.3},
        "regression": ("roe", "pb"),
    },

    "real_estate": {
        "name": "Real estate",
        "notes": "P/B approximates the discount to NAV, since investment "
                 "property is held at fair value under IFRS. Earnings include "
                 "revaluations, so P/E is excluded; P/OCF stands in for price "
                 "to recurring earnings.",
        "tickers": {
            "LAND.L": "Land Securities",
            "BLND.L": "British Land",
            "SGRO.L": "Segro",
            "LMP.L":  "LondonMetric Property",
            "BBOX.L": "Tritax Big Box",
            "UTG.L":  "Unite Group",
            "DLN.L":  "Derwent London",
            "BYG.L":  "Big Yellow Group",
            "GPE.L":  "Great Portland Estates",
            "HMSO.L": "Hammerson",
            "PHP.L":  "Primary Health Properties",
            "SAFE.L": "Safestore",
            "SHC.L":  "Shaftesbury Capital",
            "SUPR.L": "Supermarket Income REIT",
            "THRL.L": "Target Healthcare REIT",
            "WKP.L":  "Workspace Group",
            "SRE.L":  "Sirius Real Estate",
            "GRI.L":  "Grainger",
            "HWG.L":  "Harworth Group",
        },
        "valuation": {"pb": 0.5, "div_yield": 0.3, "p_ocf": 0.2},
        "quality": {"net_debt_ebitda": 0.6, "interest_cover": 0.4},
        "regression": None,
    },

    # ----- Energy, resources and utilities ---------------------------------
    "oil_gas": {
        "name": "Oil, gas & energy services",
        "notes": "Cyclical: spot multiples look cheapest at the top of the "
                 "commodity cycle, so P/E is taken on earnings averaged over "
                 "all available years. Includes Hunting (oilfield services) "
                 "and DCC (energy distribution).",
        "tickers": {
            "SHEL.L": "Shell",
            "BP.L":   "BP",
            "HBR.L":  "Harbour Energy",
            "ITH.L":  "Ithaca Energy",
            "ENOG.L": "Energean",
            "HTG.L":  "Hunting",
            "DCC.L":  "DCC",
        },
        "valuation": {"pe_avg": 0.3, "ev_ebitda": 0.3, "fcf_yield": 0.2, "shareholder_yield": 0.2},
        "quality": {"net_debt_ebitda": 0.4, "roic": 0.3, "cash_conversion": 0.3},
        "regression": None,
    },

    "mining": {
        "name": "Mining",
        "notes": "Highly cyclical, and most report in USD (converted to GBP "
                 "here). P/E uses averaged earnings, as for oil & gas. "
                 "Precious-metal and base-metal miners are mixed together.",
        "tickers": {
            "RIO.L":  "Rio Tinto",
            "GLEN.L": "Glencore",
            "AAL.L":  "Anglo American",
            "ANTO.L": "Antofagasta",
            "FRES.L": "Fresnillo",
            "EDV.L":  "Endeavour Mining",
            "HOC.L":  "Hochschild Mining",
            "PAF.L":  "Pan African Resources",
            "ATYM.L": "Atalaya Mining",
        },
        "valuation": {"pe_avg": 0.35, "ev_ebitda": 0.35, "fcf_yield": 0.3},
        "quality": {"op_margin": 0.3, "net_debt_ebitda": 0.3, "roic": 0.2, "piotroski": 0.2},
        "regression": ("op_margin", "ev_ebitda"),
    },

    "chemicals_materials": {
        "name": "Chemicals & materials",
        "notes": "Speciality chemicals, packaging and refractories. Cyclical "
                 "end markets, so P/E uses averaged earnings.",
        "tickers": {
            "CRDA.L": "Croda International",
            "JMAT.L": "Johnson Matthey",
            "MNDI.L": "Mondi",
            "ELM.L":  "Elementis",
            "VCT.L":  "Victrex",
            "RHIM.L": "RHI Magnesita",
        },
        "valuation": {"ev_ebitda": 0.35, "pe_avg": 0.3, "fcf_yield": 0.35},
        "quality": {"op_margin": 0.3, "roic": 0.3, "net_debt_ebitda": 0.2, "piotroski": 0.2},
        "regression": ("op_margin", "ev_ebitda"),
    },

    "utilities": {
        "name": "Utilities",
        "notes": "Regulated returns make these bond-like, so valuations move "
                 "with gilt yields. EV/EBIT is used because depreciation on "
                 "network assets is a real cost. Telecom Plus is included as "
                 "a multi-utility supplier.",
        "tickers": {
            "NG.L":  "National Grid",
            "SSE.L": "SSE",
            "UU.L":  "United Utilities",
            "SVT.L": "Severn Trent",
            "PNN.L": "Pennon Group",
            "CNA.L": "Centrica",
            "DRX.L": "Drax Group",
            "TEP.L": "Telecom Plus",
        },
        "valuation": {"ev_ebit": 0.4, "div_yield": 0.35, "pb": 0.25},
        "quality": {"net_debt_ebitda": 0.4, "interest_cover": 0.3, "dividend_cover": 0.3},
        "regression": None,
    },

    # ----- Consumer ---------------------------------------------------------
    "food_retail": {
        "name": "Food retail",
        "notes": "Thin margins, so small margin changes move valuations a lot. "
                 "Lease-heavy: EBITDA is after IFRS 16, so compare within "
                 "this group only.",
        "tickers": {
            "TSCO.L": "Tesco",
            "SBRY.L": "Sainsbury's",
            "MKS.L":  "Marks & Spencer",
            "OCDO.L": "Ocado Group",
            "GRG.L":  "Greggs",
        },
        "valuation": {"ev_ebitda": 0.3, "pe": 0.3, "fcf_yield": 0.25, "ev_sales": 0.15},
        "quality": {"op_margin": 0.3, "roic": 0.3, "margin_trend": 0.2, "cash_conversion": 0.2},
        "regression": ("op_margin", "ev_sales"),
    },

    "general_retail": {
        "name": "General retail & consumer brands",
        "notes": "A broad group from discounters to luxury brands. Lease-heavy, "
                 "so EBITDA is after IFRS 16. Consider splitting luxury "
                 "(Burberry, Watches of Switzerland) from mass-market retail.",
        "tickers": {
            "NXT.L":  "Next",
            "ABF.L":  "Associated British Foods",
            "KGF.L":  "Kingfisher",
            "JD.L":   "JD Sports",
            "FRAS.L": "Frasers Group",
            "BME.L":  "B&M European Value Retail",
            "BRBY.L": "Burberry Group",
            "CURY.L": "Currys",
            "DNLM.L": "Dunelm Group",
            "INCH.L": "Inchcape",
            "WOSG.L": "Watches of Switzerland",
            "PETS.L": "Pets at Home",
            "HFD.L":  "Halfords",
            "WIX.L":  "Wickes",
            "SMWH.L": "WH Smith",
            "MOON.L": "Moonpig",
            "AO.L":   "AO World",
            "ASC.L":  "ASOS",
            "DOCS.L": "Dr. Martens",
            "THG.L":  "THG",
        },
        "valuation": {"ev_ebitda": 0.3, "pe": 0.25, "fcf_yield": 0.25, "ev_sales": 0.2},
        "quality": {"op_margin": 0.3, "roic": 0.3, "margin_trend": 0.2, "cash_conversion": 0.2},
        "regression": ("op_margin", "ev_sales"),
    },

    "staples": {
        "name": "Food, beverages & household goods",
        "notes": "Stable earnings, so P/E and FCF yield are reliable here. "
                 "Most return cash through buybacks as well as dividends. "
                 "Tobacco tends to trade at a structural discount.",
        "tickers": {
            "ULVR.L": "Unilever",
            "DGE.L":  "Diageo",
            "BATS.L": "British American Tobacco",
            "RKT.L":  "Reckitt Benckiser",
            "HLN.L":  "Haleon",
            "IMB.L":  "Imperial Brands",
            "CCEP.L": "Coca-Cola Europacific Partners",
            "CCH.L":  "Coca-Cola HBC",
            "TATE.L": "Tate & Lyle",
            "CWK.L":  "Cranswick",
            "BAG.L":  "A.G. Barr",
            "GNC.L":  "Greencore",
            "HFG.L":  "Hilton Food Group",
            "PFD.L":  "Premier Foods",
            "PRN.L":  "Princes Group",
            "APN.L":  "Applied Nutrition",
            "AEP.L":  "AEP Plantations",
        },
        "valuation": {"pe": 0.25, "ev_ebitda": 0.25, "fcf_yield": 0.25, "shareholder_yield": 0.25},
        "quality": {"gross_margin": 0.3, "roic": 0.3, "net_debt_ebitda": 0.2, "dividend_cover": 0.2},
        "regression": ("roic", "ev_ebitda"),
    },

    "travel_leisure": {
        "name": "Travel & leisure",
        "notes": "Airlines, hotels, pubs, restaurants, gaming and leisure. "
                 "Mixed business models; consider splitting airlines and "
                 "gaming out if the spread of multiples is too wide.",
        "tickers": {
            "IHG.L":  "IHG Hotels & Resorts",
            "IAG.L":  "International Airlines Group",
            "EZJ.L":  "easyJet",
            "WTB.L":  "Whitbread",
            "ENT.L":  "Entain",
            "GAW.L":  "Games Workshop",
            "WIZZ.L": "Wizz Air",
            "FGP.L":  "FirstGroup",
            "TRN.L":  "Trainline",
            "MAB.L":  "Mitchells & Butlers",
            "JDW.L":  "J D Wetherspoon",
            "DOM.L":  "Domino's Pizza Group",
            "SSPG.L": "SSP Group",
            "BOWL.L": "Hollywood Bowl",
            "RNK.L":  "Rank Group",
            "PTEC.L": "Playtech",
            "PPH.L":  "PPHE Hotel Group",
            "YNGA.L": "Young's",
            "SAGA.L": "Saga",
            "MEGP.L": "ME Group International",
        },
        "valuation": {"ev_ebitda": 0.35, "pe": 0.3, "fcf_yield": 0.35},
        "quality": {"op_margin": 0.3, "roic": 0.2, "net_debt_ebitda": 0.3, "revenue_growth": 0.2},
        "regression": ("op_margin", "ev_ebitda"),
    },

    # ----- Health care --------------------------------------------------------
    "healthcare": {
        "name": "Pharma & healthcare",
        "notes": "Pipeline value is not captured by trailing multiples, so "
                 "forward P/E is included (current snapshot only, with no "
                 "history). Loss-making biotechs will rank as expensive on "
                 "earnings measures.",
        "tickers": {
            "AZN.L":  "AstraZeneca",
            "GSK.L":  "GSK",
            "HIK.L":  "Hikma Pharmaceuticals",
            "SN.L":   "Smith & Nephew",
            "CTEC.L": "ConvaTec",
            "GNS.L":  "Genus",
            "CVSG.L": "CVS Group",
            "SPI.L":  "Spire Healthcare",
            "ONT.L":  "Oxford Nanopore Technologies",
            "OXB.L":  "Oxford Biomedica",
        },
        "valuation": {"pe": 0.3, "fwd_pe": 0.2, "ev_ebit": 0.25, "fcf_yield": 0.25},
        "quality": {"op_margin": 0.3, "gross_margin": 0.3, "roic": 0.2, "revenue_growth": 0.2},
        "regression": ("op_margin", "ev_ebit"),
    },

    # ----- Industrials --------------------------------------------------------
    "aerospace_defence": {
        "name": "Aerospace & defence",
        "notes": "Long-cycle contracts and rising defence budgets mean forward "
                 "earnings matter, so forward P/E is included.",
        "tickers": {
            "BA.L":   "BAE Systems",
            "RR.L":   "Rolls-Royce",
            "MRO.L":  "Melrose Industries",
            "BAB.L":  "Babcock International",
            "QQ.L":   "QinetiQ",
            "CHG.L":  "Chemring Group",
            "AVON.L": "Avon Technologies",
        },
        "valuation": {"ev_ebit": 0.35, "pe": 0.25, "fwd_pe": 0.15, "fcf_yield": 0.25},
        "quality": {"op_margin": 0.3, "roic": 0.3, "cash_conversion": 0.2, "revenue_growth": 0.2},
        "regression": ("roic", "ev_ebit"),
    },

    "industrial_engineering": {
        "name": "Industrial engineering & electronics",
        "notes": "Engineering, instrumentation and electronic components. "
                 "EV/EBIT is used because these businesses carry real "
                 "depreciation. Metlen operates mainly in Greece.",
        "tickers": {
            "SMIN.L": "Smiths Group",
            "IMI.L":  "IMI",
            "WEIR.L": "Weir Group",
            "SPX.L":  "Spirax Group",
            "HLMA.L": "Halma",
            "MTLN.L": "Metlen Energy & Metals",
            "RS1.L":  "RS Group",
            "ROR.L":  "Rotork",
            "RSW.L":  "Renishaw",
            "OXIG.L": "Oxford Instruments",
            "HILS.L": "Hill & Smith",
            "BOY.L":  "Bodycote",
            "MGAM.L": "Morgan Advanced Materials",
            "VSVS.L": "Vesuvius",
            "COA.L":  "Coats Group",
            "GDWN.L": "Goodwin",
            "DSCV.L": "discoverIE",
            "VLX.L":  "Volex",
            "XPP.L":  "XP Power",
            "CWR.L":  "Ceres Power",
        },
        "valuation": {"ev_ebit": 0.4, "pe": 0.3, "fcf_yield": 0.3},
        "quality": {"op_margin": 0.3, "roic": 0.3, "margin_trend": 0.2, "cash_conversion": 0.2},
        "regression": ("roic", "ev_ebit"),
    },

    "construction": {
        "name": "Construction & building materials",
        "notes": "Contractors run on thin margins and hold large customer "
                 "cash balances, which flatters EV. Materials and merchants "
                 "are more cyclical. Consider splitting contractors out.",
        "tickers": {
            "BBY.L":  "Balfour Beatty",
            "HWDN.L": "Howdens Joinery",
            "MGNS.L": "Morgan Sindall",
            "TPK.L":  "Travis Perkins",
            "GFTU.L": "Grafton Group",
            "BREE.L": "Breedon Group",
            "GEN.L":  "Genuit Group",
            "FAN.L":  "Volution Group",
            "KLR.L":  "Keller Group",
            "KIE.L":  "Kier Group",
            "GFRD.L": "Galliford Try",
            "COST.L": "Costain Group",
        },
        "valuation": {"ev_ebit": 0.35, "pe": 0.3, "fcf_yield": 0.35},
        "quality": {"op_margin": 0.3, "roic": 0.3, "cash_conversion": 0.2, "net_debt_ebitda": 0.2},
        "regression": ("roic", "ev_ebit"),
    },

    "housebuilders": {
        "name": "Housebuilders",
        "notes": "Valued mainly on tangible book, since land banks are the "
                 "core asset. Earnings are highly cyclical, so P/E uses "
                 "averaged earnings.",
        "tickers": {
            "BTRW.L": "Barratt Redrow",
            "PSN.L":  "Persimmon",
            "TW.L":   "Taylor Wimpey",
            "BKG.L":  "Berkeley Group",
            "BWY.L":  "Bellway",
            "VTY.L":  "Vistry Group",
        },
        "valuation": {"ptbv": 0.45, "pe_avg": 0.3, "div_yield": 0.25},
        "quality": {"rote": 0.4, "op_margin": 0.3, "piotroski": 0.3},
        "regression": ("rote", "ptbv"),
    },

    "support_services": {
        "name": "Business & support services",
        "notes": "Outsourcing, testing, data, recruitment and distribution. "
                 "Mostly asset-light, so cash conversion and ROIC matter. "
                 "Recruiters (Hays, PageGroup) are highly cyclical.",
        "tickers": {
            "CPG.L":  "Compass Group",
            "EXPN.L": "Experian",
            "RTO.L":  "Rentokil Initial",
            "BNZL.L": "Bunzl",
            "ITRK.L": "Intertek",
            "DPLM.L": "Diploma",
            "SRP.L":  "Serco",
            "MTO.L":  "Mitie",
            "IWG.L":  "International Workplace Group",
            "HAS.L":  "Hays",
            "PAGE.L": "PageGroup",
            "JSG.L":  "Johnson Service Group",
            "ZIG.L":  "Zigup",
            "CKN.L":  "Clarkson",
            "SVS.L":  "Savills",
            "XPS.L":  "XPS Pensions Group",
        },
        "valuation": {"ev_ebit": 0.35, "pe": 0.3, "fcf_yield": 0.35},
        "quality": {"op_margin": 0.25, "roic": 0.25, "cash_conversion": 0.25, "revenue_growth": 0.25},
        "regression": ("roic", "ev_ebit"),
    },

    # ----- Technology, media and telecoms -------------------------------------
    "software_tech": {
        "name": "Software & technology",
        "notes": "Growth matters more than in most sectors, so EV/Sales is "
                 "judged against revenue growth. IT resellers (Computacenter, "
                 "Softcat, Bytes) have much lower margins than software firms.",
        "tickers": {
            "SGE.L":  "Sage Group",
            "CCC.L":  "Computacenter",
            "SCT.L":  "Softcat",
            "BYIT.L": "Bytes Technology",
            "KNOS.L": "Kainos",
            "NCC.L":  "NCC Group",
            "ALFA.L": "Alfa Financial Software",
            "ATG.L":  "Auction Technology Group",
            "RPI.L":  "Raspberry Pi",
            "TRST.L": "Trustpilot",
        },
        "valuation": {"ev_ebit": 0.3, "pe": 0.2, "fcf_yield": 0.3, "ev_sales": 0.2},
        "quality": {"op_margin": 0.25, "revenue_growth": 0.3, "roic": 0.2, "cash_conversion": 0.25},
        "regression": ("revenue_growth", "ev_sales"),
    },

    "media": {
        "name": "Media, publishing & online platforms",
        "notes": "Information businesses, classifieds platforms, publishers "
                 "and agencies. The platforms carry very high margins and "
                 "trade at premium multiples.",
        "tickers": {
            "REL.L":  "RELX",
            "INF.L":  "Informa",
            "AUTO.L": "Auto Trader",
            "PSON.L": "Pearson",
            "WPP.L":  "WPP",
            "RMV.L":  "Rightmove",
            "ITV.L":  "ITV",
            "BCG.L":  "Baltic Classifieds",
            "MONY.L": "MONY Group",
            "FOUR.L": "4imprint",
            "BMY.L":  "Bloomsbury Publishing",
            "DATA.L": "GlobalData",
        },
        "valuation": {"ev_ebit": 0.35, "pe": 0.3, "fcf_yield": 0.35},
        "quality": {"op_margin": 0.3, "roic": 0.2, "revenue_growth": 0.25, "margin_trend": 0.25},
        "regression": ("op_margin", "ev_ebit"),
    },

    "telecoms": {
        "name": "Telecoms",
        "notes": "Capital-heavy networks: leverage and free cash flow after "
                 "capex matter more than earnings. Airtel Africa and Helios "
                 "Towers operate mainly in Africa.",
        "tickers": {
            "VOD.L":  "Vodafone",
            "BT-A.L": "BT Group",
            "AAF.L":  "Airtel Africa",
            "HTWS.L": "Helios Towers",
            "GAMA.L": "Gamma Communications",
        },
        "valuation": {"ev_ebitda": 0.4, "fcf_yield": 0.35, "div_yield": 0.25},
        "quality": {"net_debt_ebitda": 0.4, "op_margin": 0.3, "revenue_growth": 0.3},
        "regression": None,
    },
}



# ---------------------------------------------------------------------------
# Macro regime and sector outlook
# ---------------------------------------------------------------------------
# The regime you expect over roughly the next 12-24 months, and how each
# sector's profitability is expected to fare in it, from -2 (contracts
# sharply) to +2 (benefits strongly). These are judgemental priors, not
# estimates: change them to match your own view. Sectors are ranked on
# score in the report; equal scores share a rank.
#
# The outlook is shown alongside the stock scores but does not change them
# or the composite.

REGIME = {
    "name": "Reflation with tightening and high bond yields",
    "description": "Growth rising, inflation rising, interest rates rising, "
                   "very high bond yields",
}

SECTOR_OUTLOOK = {
    "banks": (2.0,
        "Higher rates and a steep yield curve widen margins, and the structural "
        "hedge reinvests at much higher yields. Growth keeps loan losses low."),
    "insurance": (1.5,
        "High yields lift investment income, strengthen solvency and drive "
        "demand for pension buy-outs. Asset-management arms are a drag."),
    "oil_gas": (1.5,
        "Firm demand and commodity-led inflation support cash flow. Low "
        "leverage limits the hit from financing costs; windfall tax caps upside."),
    "mining": (1.0,
        "Industrial metals benefit from growth and inflation, but high real "
        "yields weigh on gold and silver, and capital projects cost more to fund."),
    "industrial_engineering": (0.5,
        "Pricing power and a capex upturn help, but customers face higher "
        "financing costs for new projects."),
    "aerospace_defence": (0.5,
        "Defence budgets are committed and higher yields shrink pension "
        "deficits, but fixed-price contracts are exposed to cost inflation."),
    "media": (0.5,
        "Advertising rises with growth and information businesses have pricing "
        "power. Profits are fine; premium valuations are the risk."),
    "chemicals_materials": (0.0,
        "Volume recovery is offset by energy costs and more expensive "
        "financing for a capital-intensive industry."),
    "financial_services": (0.0,
        "Platforms earn more on client cash and brokers gain from volatility, "
        "but bond-heavy managers and private-equity firms suffer."),
    "support_services": (0.0,
        "Recruiters gain from tight labour markets, but high gilt yields "
        "pressure public spending that outsourcers depend on."),
    "food_retail": (0.0,
        "Defensive volumes and some inflation pass-through, against thin "
        "margins and rising wage costs."),
    "healthcare": (0.0,
        "Profits are largely acyclical. High discount rates hit valuations "
        "of long-dated pipelines, not current profitability."),
    "software_tech": (0.0,
        "Recurring revenue keeps profits resilient. The sector is most "
        "exposed to valuation compression from high discount rates."),
    "staples": (-0.5,
        "Input-cost inflation compresses margins, and as bond proxies these "
        "shares compete directly with high gilt yields."),
    "travel_leisure": (-0.5,
        "Mortgage costs squeeze discretionary spending, while labour and "
        "energy costs rise. Leveraged pub and leisure groups are most exposed."),
    "general_retail": (-1.0,
        "Households refinancing onto much higher mortgage rates cut "
        "discretionary spending, while wage and business-rate costs rise."),
    "construction": (-1.0,
        "Housing-linked merchants and materials suffer, and high gilt yields "
        "constrain public infrastructure spending."),
    "telecoms": (-1.5,
        "Heavy debt makes refinancing much costlier, and UK rules now prevent "
        "inflation-linked mid-contract price rises."),
    "utilities": (-1.5,
        "Heavy borrowing reprices quickly while allowed regulatory returns "
        "reset only at the next price control. Bond-proxy shares de-rate."),
    "real_estate": (-2.0,
        "Very high bond yields push property yields up and valuations down, "
        "refinancing costs jump and loan-to-value covenants come under strain."),
    "housebuilders": (-2.0,
        "Mortgage rates track swap rates, so affordability, volumes and prices "
        "fall sharply while build costs rise."),
}


def sector_ranks() -> dict:
    """{sector key: (rank, score)}, rank 1 = best placed; ties share a rank."""
    scores = {k: v[0] for k, v in SECTOR_OUTLOOK.items()}
    ranks = {}
    for key, score in scores.items():
        ranks[key] = (1 + sum(1 for v in scores.values() if v > score), score)
    return ranks


def validate_config():
    """Fail fast on typos in metric names or weights."""
    problems = []
    for key, sector in SECTORS.items():
        for group in ("valuation", "quality"):
            for metric in sector[group]:
                if metric not in METRICS:
                    problems.append(f"{key}: unknown metric '{metric}' in {group}")
        for metric in sector["valuation"]:
            if metric in METRICS and METRICS[metric]["kind"] == "quality":
                problems.append(f"{key}: quality metric '{metric}' listed under valuation")
        for metric in sector["quality"]:
            if metric in METRICS and METRICS[metric]["kind"] != "quality":
                problems.append(f"{key}: valuation metric '{metric}' listed under quality")
        reg = sector.get("regression")
        if reg:
            for metric in reg:
                if metric not in METRICS:
                    problems.append(f"{key}: unknown metric '{metric}' in regression")
            if reg[1] in METRICS and METRICS[reg[1]]["kind"] != "valuation":
                problems.append(f"{key}: regression y '{reg[1]}' must be a valuation multiple")
    for metric, spec in METRICS.items():
        if spec["kind"] == "valuation" and "yield_label" not in spec:
            problems.append(f"{metric}: valuation metric needs a yield_label")
        if spec["kind"] == "quality" and "higher_is_better" not in spec:
            problems.append(f"{metric}: quality metric needs higher_is_better")
    for key in SECTORS:
        if key not in SECTOR_OUTLOOK:
            problems.append(f"{key}: missing from SECTOR_OUTLOOK")
    for key, (score, _) in SECTOR_OUTLOOK.items():
        if key not in SECTORS:
            problems.append(f"SECTOR_OUTLOOK has unknown sector '{key}'")
        if not -2 <= score <= 2:
            problems.append(f"SECTOR_OUTLOOK['{key}'] score must be between -2 and 2")
    seen = {}
    for key, sector in SECTORS.items():
        for ticker in sector["tickers"]:
            if ticker in seen:
                problems.append(f"{ticker} appears in both {seen[ticker]} and {key}")
            seen[ticker] = key
    if problems:
        raise ValueError("Config problems:\n  " + "\n  ".join(problems))
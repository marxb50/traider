from .ifr2 import IFR2Strategy
from .setup_123 import Setup123Strategy
from .inside_bar import InsideBarStrategy
from .supertrend import SupertrendStrategy
from .donchian import DonchianStrategy
from .bollinger import BollingerStrategy
from .trap_na_media import TrapNaMediaStrategy
from .pfr import PFRStrategy
from .ema_cross import EMACrossStrategy
from .ema20_pullback import EMA20PullbackStrategy
from .macd_cross import MACDCrossStrategy
from .bullish_engulfing import BullishEngulfingStrategy
from .hammer import HammerStrategy
from .volume_breakout import VolumeBreakoutStrategy
from .rsi50_retomada import RSI50RetomadaStrategy
from .additional_setups import (
    ADXTrendPullbackStrategy,
    CCIReversalStrategy,
    DoubleTopBottomBreakoutStrategy,
    EMA921CrossStrategy,
    GapContinuationStrategy,
    GapFadeStrategy,
    KeltnerBreakoutStrategy,
    MarubozuContinuationStrategy,
    MFIReversalStrategy,
    NR7BreakoutStrategy,
    OBVBreakoutStrategy,
    PinBarReversalStrategy,
    ROCMomentumStrategy,
    SMA2050CrossStrategy,
    SqueezeBreakoutStrategy,
    StochasticCrossStrategy,
    ThreeBarReversalStrategy,
    VWAPPullbackStrategy,
    VWAPReclaimStrategy,
    WilliamsRReversalStrategy,
)

STRATEGY_REGISTRY = {
    cls.name: cls for cls in [
        IFR2Strategy,
        Setup123Strategy,
        InsideBarStrategy,
        SupertrendStrategy,
        DonchianStrategy,
        BollingerStrategy,
        TrapNaMediaStrategy,
        PFRStrategy,
        EMACrossStrategy,
        EMA20PullbackStrategy,
        MACDCrossStrategy,
        BullishEngulfingStrategy,
        HammerStrategy,
        VolumeBreakoutStrategy,
        RSI50RetomadaStrategy,
        SMA2050CrossStrategy,
        EMA921CrossStrategy,
        VWAPReclaimStrategy,
        VWAPPullbackStrategy,
        NR7BreakoutStrategy,
        SqueezeBreakoutStrategy,
        KeltnerBreakoutStrategy,
        ADXTrendPullbackStrategy,
        CCIReversalStrategy,
        StochasticCrossStrategy,
        WilliamsRReversalStrategy,
        ROCMomentumStrategy,
        OBVBreakoutStrategy,
        MFIReversalStrategy,
        GapContinuationStrategy,
        GapFadeStrategy,
        ThreeBarReversalStrategy,
        PinBarReversalStrategy,
        MarubozuContinuationStrategy,
        DoubleTopBottomBreakoutStrategy,
    ]
}

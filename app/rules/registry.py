from app.rules.base import Rule
from app.rules.night_safety import NightSafetyRule
from app.rules.otp_drop import OtpDropRule
from app.rules.route_deviation import RouteDeviationRule
from app.rules.over_speed import OverSpeedRule
from app.rules.sos import SosRule

ACTIVE_RULES: list[Rule] = [
    NightSafetyRule(),
    OtpDropRule(),
    RouteDeviationRule(),
    OverSpeedRule(),
    SosRule()
]

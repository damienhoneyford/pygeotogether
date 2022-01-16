"""Commonly used types for the Geo Together functionality."""
from enum import Enum
from datetime import date
import re
from dateutil.relativedelta import relativedelta

class EnumWithDescription(Enum):
    """
    Enhanced Enum that allows each member to have a description and allows
    values to be looked up in a case-insensitive way.
    """
    def __init__(self, _value, description: str = None) -> None:
        # Don't need to do anything with value as __new__ will handle it
        self._description = description

    def __new__(cls, *args, **_kwargs):
        rtn = object.__new__(cls)
        rtn._value_ = args[0]
        return rtn

    def _missing_(self, value):
        if value is str:
            for possible_value in self:
                if str(possible_value).casefold() == value.casefold():
                    return possible_value
        return None

    @property
    def description(self) -> str:
        """Describes the given member of the Enum."""
        return self._description or self.value

class GeoEnergyType(EnumWithDescription):
    """Defines the energy types supported by Geo Together."""
    ELECTRICITY = "Electricity"
    GAS_ENERGY = "Gas"

class GeoPowerUnit(EnumWithDescription):
    """Defines a unit of power measurement."""
    WATT = "W", "Watts"
    KILOWATT = "kW", "Kilowatts"

class GeoEnergyUnit(EnumWithDescription):
    """Defines a unit of energy usage, i.e. power used over a given time."""
    WATT_HOUR = "Wh", "Watt Hours"
    KILOWATT_HOUR = "kWh", "Kilowatt Hours"

class GeoTimePeriod(EnumWithDescription):
    """"Defines an amount of time that energy usage can be shown for."""
    DAY = "Day"
    WEEK = "Week"
    MONTH = "Month"
    UNBILLED = "Since Last Bill"
    FOREVER = "All Time"

    def resolve(self, offset: int, start_date: date = date.today()) -> tuple[date, date]:
        """
        Resolves the current GeoTimePeriod to a concrete start / end date based on the given offset
        """
        if self is GeoTimePeriod.DAY:
            from_date = start_date + relativedelta(days=offset)
            to_date = from_date
        elif self is GeoTimePeriod.WEEK:
            from_date = start_date + relativedelta(days=-start_date.weekday(), weeks=offset)
            to_date = from_date + relativedelta(days=6)
        elif self is GeoTimePeriod.MONTH:
            from_date = start_date + relativedelta(day=1, months=offset)
            to_date = from_date + relativedelta(days=-1, months=1)
        else:
            from_date = None
            to_date = None

        return from_date, to_date

class GeoLivePowerUsage:
    """Provides details of live power usage."""
    def __init__(self, api_power_usage: dict) -> None:
        self._live_usage = api_power_usage

    @property
    def type(self) -> GeoEnergyType:
        """Specifies the type of energy this power usage relates to, e.g. gas or electric."""
        raw_type = self._live_usage["type"] if "type" in self._live_usage else None
        return GeoEnergyType[raw_type.upper()] if raw_type else None

    @property
    def unit(self) -> GeoPowerUnit:
        """Specifies the unit of measure for the power value, e.g. watts, kilowatts, etc."""
        return GeoPowerUnit.WATT if "watts" in self._live_usage else None

    @property
    def value(self) -> int:
        """Specifies the actual power usage value."""
        return self._live_usage["watts"] if "watts" in self._live_usage else None

    def __str__(self) -> str:
        return f"{self.type.value}: {self.value} {self.unit.value}"

class GeoEnergyUsage:
    """Provides details of energy usage over a period of time."""
    def __init__(self, period: GeoTimePeriod, energy_type: GeoEnergyType,
                 energy_amount: float, energy_cost: float) -> None:

        self._period = period
        self._type = energy_type
        self._energy_amount = energy_amount
        self._energy_cost = energy_cost

    @property
    def period(self) -> GeoTimePeriod:
        """Specifies the period of time this usage relates to"""
        return self._period

    @property
    def type(self) -> GeoEnergyType:
        """Specifies the energy type this usage relates to"""
        return self._type

    @property
    def unit(self) -> GeoEnergyUnit:
        """Specifies the unit of measure for the energy usage amount, e.g. wh, kwh, etc."""
        return GeoEnergyUnit.KILOWATT_HOUR

    @property
    def amount(self) -> float:
        """Specifies the actual energy used."""
        return self._energy_amount

    @property
    def cost(self) -> float:
        """Specifies the associated cost of the energy used."""
        return self._energy_cost

    def __format__(self, __format_spec: str) -> str:
        def replacer(match: re.Match):
            rtn = ""
            specifier = match.group(0)
            if specifier == "%p":
                rtn = self.period.value
            elif specifier == "%P":
                rtn = self.period.description
            elif specifier == "%t":
                rtn = self.type.value
            elif specifier == "%T":
                rtn = self.type.description
            elif specifier == "%u":
                rtn = self.unit.value
            elif specifier == "%U":
                rtn = self.unit.description
            elif specifier == "%a":
                rtn = str(self.amount)
            elif specifier == "%A":
                rtn = str(round(self.amount))
            elif specifier == "%c":
                rtn = str(self.cost)
            elif specifier == "%C":
                rtn = str(round(self.cost / 100, 2))
            return rtn

        return re.sub("%[ptuacPTUAC]", replacer, __format_spec)

    def __str__(self) -> str:
        return f"{self.period.value}: {self.amount}{self.unit.value}"

class GeoPeriodicEnergyUsage:
    """Provides details of energy usage."""
    def __init__(self, energy_type: GeoEnergyType, usage: list[GeoEnergyUsage]) -> None:
        self._type = energy_type
        self._usage = usage

    @property
    def type(self) -> GeoEnergyType:
        """Specifies the type of energy this usage relates to, e.g. gas or electric."""
        return self._type

    def get_usage(self, period: GeoTimePeriod) -> GeoEnergyUsage:
        """Retrieves usage details for the given period of time."""
        for periodic_usage in self._usage:
            if periodic_usage.period is period:
                return periodic_usage
        return None

    def __add__(self, other):
        if isinstance(other, GeoEnergyUsage):
            self._usage.append(other)
        elif isinstance(other, list):
            self._usage.extend(other)
        return self

    def __str__(self) -> str:
        return f"{self.type.value}: {self.get_usage(GeoTimePeriod.DAY)}"

class GeoTogetherError(Exception):
    """Geo Together specific error."""

class GeoTogetherAuthenticationError(GeoTogetherError):
    """Geo Together authentication specific error."""

class GeoTogetherSystemError(GeoTogetherError):
    """Geo Together system specific error."""

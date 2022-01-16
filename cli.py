"""Simple CLI for Geo Together API."""

import asyncio
from datetime import date
import click
from pygeotogether.geotogether import GeoTogetherClient
from pygeotogether.geocommon import GeoEnergyUnit, GeoEnergyUsage, GeoLivePowerUsage,\
                                    GeoPeriodicEnergyUsage, GeoTimePeriod
@click.command()
@click.option("--username", "-u", help="Username to authenticate with")
@click.option("--password", "-p", help="Password to authenticate with")
@click.option("--system", "-s", help="The system name to query, leave blank for default",
              default=None)
@click.option("--mode", "-m", help="Whether to show live, periodic or historic usage data",
              type=click.Choice(["live", "periodic", "historic"], False), default="live")
@click.option("--time", "-t", help="Time period for periodic and historic usage data",
              type=click.Choice([t.name for t in GeoTimePeriod], False), default="DAY")
@click.option("--offset", "-o", help="The offset to apply when looking up historic data",
              type=int)
def cli(username, password, system, mode, time, offset):
    """CLI for this package."""
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(handle(username, password, system, mode, time, offset))

_PERIOD_DESCRIPTIONS = {
    GeoTimePeriod.DAY: ["Today", "Yesterday", "%x"],
    GeoTimePeriod.WEEK: ["This Week", "Last Week", "Week Commencing %x"],
    GeoTimePeriod.MONTH: ["This Month", "Last Month", "%b %Y"],
    GeoTimePeriod.UNBILLED: ["Since Last Bill"],
    GeoTimePeriod.FOREVER: ["Since Last Meter Change"]
}
def _friendly_date(time_period: GeoTimePeriod, offset: int, resolved_date: date) -> str:
    """Converts the given GeoTimePeriod to a friendly date"""
    descriptions = _PERIOD_DESCRIPTIONS[time_period]
    pos = min(abs(offset), len(descriptions) - 1)

    return resolved_date.strftime(descriptions[pos])

def _print_usage(prefix: str, usage_period: str, amount: float, amount_unit: GeoEnergyUnit,
                 cost: float):
    output_usage = [prefix, " "]
    if amount > 0:
        output_usage.append(f"Usage {usage_period}: {round(amount)}{amount_unit.value}")
    if cost > 0:
        if amount > 0:
            output_usage.append(f", Cost: £{round(cost / 100, 2):.2f}")
        else:
            output_usage.append(f"Cost {usage_period}: £{round(cost / 100, 2):.2f}")
    if len(output_usage) > 1:
        print("".join(output_usage))

def _handle_live_usage(live_data: list[GeoLivePowerUsage]):
    if len(live_data) > 0:
        for power_usage in live_data:
            print(power_usage)
    else:
        print("No live power data available.")

def _handle_periodic_usage(periodic_data: list[GeoPeriodicEnergyUsage], time_period: str):
    if len(periodic_data) > 0:
        total_energy = None
        total_cost = None
        usage_date = _friendly_date(GeoTimePeriod[time_period], 0, date.today())
        for periodic_usage in periodic_data:
            usage = periodic_usage.get_usage(GeoTimePeriod[time_period])
            if usage.amount is not None:
                total_energy = (total_energy or 0) + usage.amount
            if usage.cost is not None:
                total_cost = (total_cost or 0) + usage.cost

            _print_usage(usage.type.description, usage_date, usage.amount, usage.unit, usage.cost)

        if total_energy > 0 or total_cost > 0:
            _print_usage("Total Energy", usage_date, total_energy, GeoEnergyUnit.KILOWATT_HOUR,
                         total_cost)
    else:
        print("No periodic energy data available.")

def _handle_historic_usage(historic_data: list[GeoEnergyUsage], time_period: str,
                          time_period_offset: int):
    if len(historic_data) > 0:
        total_energy = None
        total_cost = None
        usage_date = _friendly_date(GeoTimePeriod[time_period], time_period_offset,
                                    date.today())
        for usage in historic_data:
            if usage.amount is not None:
                total_energy = (total_energy or 0) + usage.amount
            if usage.cost is not None:
                total_cost = (total_cost or 0) + usage.cost

            _print_usage(usage.type.value, usage_date, usage.amount, usage.unit, usage.cost)

        _print_usage("Total Energy", usage_date, total_energy, GeoEnergyUnit.KILOWATT_HOUR,
                     total_cost)
    else:
        print("No historic energy data available.")

async def handle(username, password, system, mode, time_period, time_period_offset) -> None:
    """Asynchronous CLI handler."""
    async with GeoTogetherClient(username, password) as client:
        if await client.authenticate():
            if await client.resolve_system(system):
                if mode == "live":
                    _handle_live_usage(await client.get_live_usage())
                elif mode == "periodic":
                    _handle_periodic_usage(await client.get_periodic_usage(), time_period)
                elif mode == "historic":
                    historic_data = await client.get_historic_usage(GeoTimePeriod[time_period],
                                                                    time_period_offset)
                    _handle_historic_usage(historic_data, time_period, time_period_offset)
                else:
                    print(f"Unknown Mode: {mode}")

cli() # pylint: disable=E1120

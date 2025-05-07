import discord
from discord import app_commands
from discord.ext import commands, tasks
import aiohttp
import os
import asyncio
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from dateutil.parser import isoparse
import logging
from typing import Dict, List, Optional, Set


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# Load environment variables
load_dotenv()
PNW_API_KEY = "7d58ca300d0ac2f7b373"
DISCORD_TOKEN = "MTM1NTA2MjA3MzU3MDA5OTMwMA.GuzVw0.BK5lYiBedRodL1oY7V0XDFu79PhWFAFti_jPgo"
GRAPHQL_URL = "https://api.politicsandwar.com/graphql?api_key=" + PNW_API_KEY


# Spy Monitor Configuration
SPY_MONITOR_CONFIG = {
    "api_key": "7d58ca300d0ac2f7b373",
    "alliance_ids": [13410, 1742, 13823, 13883],
    "check_interval": 120,
    "notification_channel_id": 1103728757602267188,
    "score_range": [0.4, 1.5],
    "guild_id": 1103728755823874139,
    "attackers_per_page": 5,
    "max_pages": 10,
    "per_page": 500,
    "activity_window": 60
}


# Game constants
WAR_DATA = {
    "base_loot": 50000,
    "base_loot_percentage": 0.14,
    "pirate_bonus": 0.03
}


SEPARATOR = "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬"
MAX_NATIONS_PER_QUERY = 500
TOTAL_NATIONS_TO_FETCH = 15000
MAX_CONCURRENT_REQUESTS = 3
RESULTS_PER_PAGE = 10


BUILDING_DATA = {
    "coal_power": {"upkeep": 1200},
    "oil_power": {"upkeep": 1800},
    "nuclear_power": {"upkeep": 3000},
    "wind_power": {"upkeep": 0},
    "coal_mine": {"upkeep": 500},
    "oil_well": {"upkeep": 600},
    "uranium_mine": {"upkeep": 800},
    "iron_mine": {"upkeep": 450},
    "bauxite_mine": {"upkeep": 500},
    "lead_mine": {"upkeep": 400},
    "farm": {"upkeep": 50},
    "oil_refinery": {"upkeep": 700},
    "steel_mill": {"upkeep": 900},
    "aluminum_refinery": {"upkeep": 850},
    "munitions_factory": {"upkeep": 750},
    "police_station": {"upkeep": 300},
    "hospital": {"upkeep": 350},
    "recycling_center": {"upkeep": 400},
    "subway": {"upkeep": 500},
    "supermarket": {"upkeep": 200},
    "bank": {"upkeep": 600},
    "shopping_mall": {"upkeep": 800},
    "stadium": {"upkeep": 1000},
}


IMPROVEMENT_REVENUE = {
    "supermarket": 0.00953808026,
    "bank": 0.0144609375,
    "shopping_mall": 0.019375,
    "stadium": 0.0244140625,
    "subway": 0.019375
}


RAID_QUERY = """
query GetRaidTargets($minScore: Float, $maxScore: Float, $first: Int, $page: Int) {
    nations(
        first: $first
        page: $page
        min_score: $minScore
        max_score: $maxScore
        orderBy: {column: SCORE, order: ASC}
    ) {
        data {
            id
            nation_name
            leader_name
            score
            color
            alliance_id
            alliance {
                id
                name
                score
            }
            cities {
                id
                name
                infrastructure
                land
                powered
                coal_power
                oil_power
                nuclear_power
                wind_power
                coal_mine
                oil_well
                uranium_mine
                iron_mine
                bauxite_mine
                lead_mine
                farm
                oil_refinery
                steel_mill
                aluminum_refinery
                munitions_factory
                police_station
                hospital
                recycling_center
                subway
                supermarket
                bank
                shopping_mall
                stadium
            }
            soldiers
            tanks
            aircraft
            ships
            missiles
            nukes
            spies
            offensive_wars_count
            defensive_wars_count
            last_active
            beige_turns
            vacation_mode_turns
        }
        paginatorInfo {
            total
            currentPage
            lastPage
            perPage
        }
    }
    tradeprices(first: 1) {
        data {
            coal
            oil
            uranium
            iron
            bauxite
            lead
            gasoline
            munitions
            steel
            aluminum
            food
        }
    }
    alliances(first: 500, orderBy: {column: SCORE, order: DESC}) {
        data {
            id
            name
            score
        }
    }
}
"""


NATION_QUERY = """
query GetNation($id: [Int]!) {
    nations(id: $id) {
        data {
            id
            nation_name
            leader_name
            score
            color
            alliance_id
            alliance {
                id
                name
                score
            }
            cities {
                id
                name
                infrastructure
                land
                powered
                coal_power
                oil_power
                nuclear_power
                wind_power
                coal_mine
                oil_well
                uranium_mine
                iron_mine
                bauxite_mine
                lead_mine
                farm
                oil_refinery
                steel_mill
                aluminum_refinery
                munitions_factory
                police_station
                hospital
                recycling_center
                subway
                supermarket
                bank
                shopping_mall
                stadium
            }
            soldiers
            tanks
            aircraft
            ships
            missiles
            nukes
            spies
            offensive_wars_count
            defensive_wars_count
            last_active
            beige_turns
            vacation_mode_turns
        }
    }
    tradeprices(first: 1) {
        data {
            coal
            oil
            uranium
            iron
            bauxite
            lead
            gasoline
            munitions
            steel
            aluminum
            food
        }
    }
}
"""


class MilitaryAnalyzer:
    @staticmethod
    def calculate_strength(nation: Dict) -> float:
        if not nation:
            return 0.0
            
        strength = 0
        strength += nation.get('soldiers', 0) * 0.001
        strength += nation.get('tanks', 0) * 0.5
        strength += nation.get('aircraft', 0) * 2.5
        strength += nation.get('ships', 0) * 5.0
        strength += nation.get('missiles', 0) * 25.0
        strength += nation.get('nukes', 0) * 100.0
        strength += nation.get('spies', 0) * 1.0
        return strength


    @staticmethod
    def defense_rating(strength: float) -> str:
        if strength < 50: return "🔴 Easy"
        if strength < 150: return "🟠 Medium"
        return "🟢 Hard"


class ResourceCalculator:
    def __init__(self, trade_prices: Dict[str, float]):
        self.prices = trade_prices or {}


    def calculate_city_resources(self, city: Dict) -> float:
        if not city:
            return 0.0


        total = 0.0
        mines = {
            'coal_mine': 'coal',
            'oil_well': 'oil',
            'uranium_mine': 'uranium',
            'iron_mine': 'iron',
            'bauxite_mine': 'bauxite',
            'lead_mine': 'lead',
            'farm': 'food'
        }


        for building, resource in mines.items():
            if city.get(building, 0) > 0:
                count = city[building]
                specialization = 1 + (0.5 * (count - 1)) / (5 - 1)
                base_production = {
                    'coal_mine': 2.5,
                    'oil_well': 2.0,
                    'uranium_mine': 0.5,
                    'iron_mine': 1.5,
                    'bauxite_mine': 1.3,
                    'lead_mine': 1.0,
                    'farm': 10.0
                }.get(building, 0)
                total += count * base_production * specialization * self.prices.get(resource, 0)


        manufacturing = {
            'oil_refinery': ('oil', 'gasoline', 2.0),
            'steel_mill': (['coal', 'iron'], 'steel', 3.0),
            'aluminum_refinery': ('bauxite', 'aluminum', 3.0),
            'munitions_factory': ('lead', 'munitions', 6.0)
        }


        for building, (inputs, output, ratio) in manufacturing.items():
            if city.get(building, 0) > 0:
                count = city[building]
                specialization = 1 + (0.5 * (count - 1)) / (5 - 1)
                if isinstance(inputs, list):
                    for imp in inputs:
                        total -= count * 3 * specialization * self.prices.get(imp, 0)
                else:
                    total -= count * 3 * specialization * self.prices.get(inputs, 0)
                total += count * ratio * 3 * specialization * self.prices.get(output, 0)


        return total


class RevenueCalculator:
    def calculate_city_revenue(self, city: Dict) -> float:
        if not city:
            return 0.0
            
        population = self._calculate_population(city)
        revenue = population * 1.0


        for improvement, rate in IMPROVEMENT_REVENUE.items():
            if city.get(improvement, 0) > 0:
                revenue += population * city[improvement] * rate


        return revenue


    def _calculate_population(self, city: Dict) -> float:
        if not city:
            return 0.0


        base_pop = city.get('infrastructure', 0) * 100
        if city.get('hospital', 0) > 0:
            base_pop *= 1.02 ** city['hospital']
        if city.get('subway', 0) > 0:
            base_pop *= 1.01 ** city['subway']
        return base_pop


class RaidTargetFinder:
    def __init__(self):
        self.session = aiohttp.ClientSession()
        self.alliance_rankings = {}


    async def close(self):
        await self.session.close()


    async def fetch_targets_batch(self, min_score: float, max_score: float, first: int, page: int) -> Dict:
        try:
            async with self.session.post(
                GRAPHQL_URL,
                json={
                    "query": RAID_QUERY,
                    "variables": {
                        "minScore": min_score,
                        "maxScore": max_score,
                        "first": first,
                        "page": page
                    }
                },
                timeout=30
            ) as response:
                if response.status != 200:
                    raise Exception(f"API returned status {response.status}")
                
                data = await response.json()
                if "errors" in data:
                    raise Exception(data["errors"][0]["message"])
                
                return data.get("data", {})
                
        except Exception as e:
            logger.error(f"Error fetching targets batch: {str(e)}")
            raise


    async def fetch_targets(self, min_score: float, max_score: float) -> List[Dict]:
        try:
            initial_data = await self.fetch_targets_batch(min_score, max_score, 1, 1)
            if not initial_data:
                raise Exception("No data received from initial fetch")
                
            alliances_data = initial_data.get('alliances', {}).get('data', [])
            self.alliance_rankings = {
                a['id']: idx + 1
                for idx, a in enumerate(alliances_data)
            }


            trade_prices = initial_data.get('tradeprices', {}).get('data', [{}])[0]
            total_nations = min(TOTAL_NATIONS_TO_FETCH, MAX_NATIONS_PER_QUERY * 10)
            batches = (total_nations + MAX_NATIONS_PER_QUERY - 1) // MAX_NATIONS_PER_QUERY


            tasks = []
            for page in range(1, batches + 1):
                tasks.append(
                    self.fetch_targets_batch(
                        min_score,
                        max_score,
                        min(MAX_NATIONS_PER_QUERY, total_nations - (page-1)*MAX_NATIONS_PER_QUERY),
                        page
                    )
                )


            nations = []
            for i in range(0, len(tasks), MAX_CONCURRENT_REQUESTS):
                batch_tasks = tasks[i:i+MAX_CONCURRENT_REQUESTS]
                results = await asyncio.gather(*batch_tasks, return_exceptions=True)
                
                for result in results:
                    if isinstance(result, Exception):
                        logger.error(f"Error in batch fetch: {str(result)}")
                        continue
                    
                    nations_data = result.get('nations', {}).get('data', [])
                    if nations_data:
                        nations.extend(nations_data)


            return nations, trade_prices
            
        except Exception as e:
            logger.error(f"Error in fetch_targets: {str(e)}")
            raise


    async def fetch_nation(self, nation_id: int) -> Dict:
        try:
            async with self.session.post(
                GRAPHQL_URL,
                json={
                    "query": NATION_QUERY,
                    "variables": {"id": [nation_id]}
                },
                timeout=30
            ) as response:
                if response.status != 200:
                    raise Exception(f"API returned status {response.status}")
                
                data = await response.json()
                if "errors" in data:
                    raise Exception(data["errors"][0]["message"])
                
                return data.get("data", {})
                
        except Exception as e:
            logger.error(f"Error fetching nation {nation_id}: {str(e)}")
            raise


    async def analyze_targets(self, nations: List[Dict], trade_prices: Dict, number_of_results: int = 10) -> List[Dict]:
        analyzed = []
        rc = ResourceCalculator(trade_prices)
        rvc = RevenueCalculator()
        
        for nation in nations:
            try:
                if not nation or not isinstance(nation, dict):
                    logger.warning(f"Skipping invalid nation data: {nation}")
                    continue
                    
                if nation.get('vacation_mode_turns', 0) > 0:
                    continue


                if nation.get('beige_turns', 0) > 0:
                    continue


                if nation.get('defensive_wars_count', 0) >= 3:
                    continue


                if not nation.get('cities'):
                    logger.warning(f"Nation {nation.get('id')} has no cities data")
                    continue


                military = MilitaryAnalyzer.calculate_strength(nation)
                loot = await self.calculate_loot(nation, rc, rvc)
                activity = self.calculate_activity_score(nation)
                
                alliance_data = nation.get('alliance', {}) or {}
                alliance_name = alliance_data.get('name', 'None')
                alliance_rank = self.alliance_rankings.get(nation.get('alliance_id'), 'N/A')


                analyzed.append({
                    "nation": nation,
                    "score": nation.get('score', 0),
                    "military": military,
                    "loot": loot,
                    "activity": activity,
                    "alliance_name": alliance_name,
                    "alliance_rank": alliance_rank
                })
            except Exception as e:
                logger.error(f"Error analyzing nation {nation.get('id', 'UNKNOWN')}: {str(e)}. Nation data: {nation}")
                continue


        analyzed.sort(key=lambda x: (-x['loot']['total'], x['military'], x['activity']))
        return analyzed[:number_of_results]


    async def analyze_nation(self, nation: Dict, trade_prices: Dict) -> Dict:
        if not nation:
            return {
                "nation": {},
                "score": 0,
                "military": 0,
                "loot": {
                    "total": 0,
                    "resources": 0,
                    "revenue": 0,
                    "upkeep": 0,
                    "base": WAR_DATA['base_loot'],
                    "percentage": WAR_DATA['base_loot_percentage']
                },
                "activity": 0,
                "alliance_name": "None",
                "alliance_rank": "N/A"
            }


        rc = ResourceCalculator(trade_prices)
        rvc = RevenueCalculator()
        military = MilitaryAnalyzer.calculate_strength(nation)
        loot = await self.calculate_loot(nation, rc, rvc)
        activity = self.calculate_activity_score(nation)
        
        alliance_data = nation.get('alliance', {}) or {}
        alliance_name = alliance_data.get('name', 'None')
        alliance_rank = self.alliance_rankings.get(nation.get('alliance_id'), 'N/A')


        return {
            "nation": nation,
            "score": nation.get('score', 0),
            "military": military,
            "loot": loot,
            "activity": activity,
            "alliance_name": alliance_name,
            "alliance_rank": alliance_rank
        }


    async def calculate_loot(self, nation: Dict, rc: ResourceCalculator, rvc: RevenueCalculator) -> Dict:
        if not nation or not nation.get('cities'):
            return {
                "total": 0,
                "resources": 0,
                "revenue": 0,
                "upkeep": 0,
                "base": WAR_DATA['base_loot'],
                "percentage": WAR_DATA['base_loot_percentage']
            }


        total_resources = 0.0
        total_revenue = 0.0
        total_upkeep = 0.0
        days_inactive = 1


        if nation.get('last_active'):
            try:
                last_active_date = isoparse(nation['last_active']).astimezone(timezone.utc)
                days_inactive = (datetime.now(timezone.utc) - last_active_date).days
                days_inactive = max(days_inactive, 1)
            except Exception as e:
                logger.error(f"Error parsing last_active for nation {nation.get('id')}: {str(e)}")


        for city in nation.get('cities', []):
            total_resources += rc.calculate_city_resources(city) * days_inactive
            total_revenue += rvc.calculate_city_revenue(city) * days_inactive
            total_upkeep += self.calculate_city_upkeep(city) * days_inactive


        base_loot = WAR_DATA['base_loot']
        loot_percentage = WAR_DATA['base_loot_percentage']
        total_loot = (base_loot + total_resources) + (total_revenue * loot_percentage)
        net_loot = max(total_loot - total_upkeep, 0)


        return {
            "total": net_loot,
            "resources": total_resources,
            "revenue": total_revenue,
            "upkeep": total_upkeep,
            "base": base_loot,
            "percentage": loot_percentage
        }


    def calculate_city_upkeep(self, city: Dict) -> float:
        if not city:
            return 0.0
        return sum(city.get(building, 0) * data["upkeep"] for building, data in BUILDING_DATA.items())


    def calculate_activity_score(self, nation: Dict) -> float:
        if not nation or not nation.get('last_active'):
            return 1.0  # Treat as inactive if no data


        try:
            last_active = isoparse(nation['last_active'])
            days_inactive = (datetime.now(timezone.utc) - last_active).days
            return min(days_inactive / 7.0, 1.0)
        except Exception as e:
            logger.error(f"Error calculating activity score for nation {nation.get('id')}: {str(e)}")
            return 1.0


class AttackersPaginator(discord.ui.View):
    def __init__(self, attacker_data: List[Dict], victim_data: Dict, nation_data: Dict, check_time: datetime):
        super().__init__(timeout=600)
        self.attacker_data = attacker_data
        self.victim_data = victim_data
        self.nation_data = nation_data
        self.check_time = check_time
        self.current_page = 0
        self.max_page = max(0, (len(attacker_data) - 1) // SPY_MONITOR_CONFIG["attackers_per_page"])
        self.update_buttons()


    def update_buttons(self):
        self.previous_button.disabled = self.current_page <= 0
        self.next_button.disabled = self.current_page >= self.max_page


    def create_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title=f"🚨 Spy Loss - {self.victim_data['nation_name']}",
            color=discord.Color.red(),
            url=f"https://politicsandwar.com/nation/id={self.victim_data['id']}",
            timestamp=self.check_time
        )
        
        prev_spies = self.nation_data.get(self.victim_data["id"], {}).get("last_spies", "?")
        current_spies = self.victim_data.get("spies", "?")
        
        embed.add_field(name="Victim", value=f"[{self.victim_data['nation_name']}](https://politicsandwar.com/nation/id={self.victim_data['id']})", inline=False)
        embed.add_field(name="Spies", value=f"{prev_spies} → {current_spies}", inline=True)
        embed.add_field(name="Score", value=f"{self.victim_data['score']:.2f}", inline=True)
        
        alliance = self.victim_data.get('alliance', {})
        embed.add_field(name="Alliance", value=f"[{alliance.get('name', 'None')}](https://politicsandwar.com/alliance/id={alliance.get('id', 0)})", inline=False)
        
        start_idx = self.current_page * SPY_MONITOR_CONFIG["attackers_per_page"]
        page_attackers = self.attacker_data[start_idx:start_idx + SPY_MONITOR_CONFIG["attackers_per_page"]]
        
        attackers_text = []
        for idx, attacker in enumerate(page_attackers, start=start_idx+1):
            alliance_name = attacker.get('alliance', {}).get('name', 'None')
            attackers_text.append(
                f"{idx}. [{attacker['nation_name']}](https://politicsandwar.com/nation/id={attacker['id']}) "
                f"({alliance_name}) - {attacker['score']:.2f}"
            )
        
        embed.add_field(
            name=f"Potential Attackers ({len(self.attacker_data)} total)",
            value="\n".join(attackers_text) if attackers_text else "None found",
            inline=False
        )
        
        embed.set_footer(text=f"Page {self.current_page + 1}/{self.max_page + 1}")
        return embed


    @discord.ui.button(emoji="⬅️", style=discord.ButtonStyle.grey)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)


    @discord.ui.button(emoji="➡️", style=discord.ButtonStyle.grey)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)


class PnWBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix="!", intents=intents, case_insensitive=True)
        self.session = None
        self.nation_data = {}
        self.processed_spy_losses = set()


    async def setup_hook(self):
        self.session = aiohttp.ClientSession()
        self.monitor.start()


    async def close(self):
        if self.session:
            await self.session.close()
        await super().close()


    async def fetch_paginated_nations(self, min_score: float, max_score: float) -> List[Dict]:
        all_nations = []
        
        for page in range(1, SPY_MONITOR_CONFIG["max_pages"] + 1):
            query = """
            query GetPotentialAttackers($min_score: Float!, $max_score: Float!, $page: Int!, $per_page: Int!) {
                nations(
                    min_score: $min_score
                    max_score: $max_score
                    page: $page
                    first: $per_page
                    orderBy: [{column: SCORE, order: DESC}]
                ) {
                    paginatorInfo {
                        hasMorePages
                    }
                    data {
                        id
                        nation_name
                        score
                        last_active
                        alliance { id name }
                        war_policy
                    }
                }
            }
            """
            variables = {
                "min_score": min_score,
                "max_score": max_score,
                "page": page,
                "per_page": SPY_MONITOR_CONFIG["per_page"]
            }
            
            data = await self.fetch_graphql(query, variables)
            if not data:
                break
                
            nations = data.get("data", {}).get("nations", {})
            all_nations.extend(nations.get("data", []))
            
            if not nations.get("paginatorInfo", {}).get("hasMorePages", False):
                break
                
            await asyncio.sleep(1)
            
        return all_nations


    async def fetch_graphql(self, query: str, variables: Dict = None) -> Optional[Dict]:
        try:
            url = f"https://api.politicsandwar.com/graphql?api_key={SPY_MONITOR_CONFIG['api_key']}"
            async with self.session.post(
                url,
                json={"query": query, "variables": variables or {}},
                timeout=30
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    print(f"API Error {response.status}: {error_text}")
                    return None
                return await response.json()
        except Exception as e:
            print(f"Network error: {str(e)}")
            return None


    async def get_alliance_nations(self) -> List[Dict]:
        query = """
        query GetAllianceNations($alliance_ids: [Int!]) {
            nations(
                alliance_id: $alliance_ids
                first: 500
                orderBy: [{column: ID, order: ASC}]
            ) {
                data {
                    id
                    nation_name
                    leader_name
                    score
                    spies
                    last_active
                    discord_id
                    alliance { id name acronym }
                    war_policy
                    num_cities
                }
            }
        }
        """
        data = await self.fetch_graphql(query, {"alliance_ids": SPY_MONITOR_CONFIG["alliance_ids"]})
        return data.get("data", {}).get("nations", {}).get("data", []) if data else []


    def was_active_at_exact_time(self, last_active: str, check_time: datetime) -> bool:
        if not last_active:
            return False
        try:
            if last_active.endswith('Z'):
                active_time = datetime.fromisoformat(last_active[:-1] + '+00:00')
            else:
                active_time = datetime.fromisoformat(last_active)
            
            if active_time.tzinfo is None:
                active_time = active_time.replace(tzinfo=timezone.utc)
            
            return abs((check_time - active_time).total_seconds()) <= SPY_MONITOR_CONFIG["activity_window"]
        except ValueError:
            return False


    async def send_alert(self, channel: discord.TextChannel, victim: Dict, attackers: List[Dict], check_time: datetime):
        if not attackers:
            await channel.send(f"No active attackers found for {victim['nation_name']} at check time")
            return
            
        paginator = AttackersPaginator(attackers, victim, self.nation_data, check_time)
        mention = f"<@{victim['discord_id']}>" if victim.get("discord_id") else ""
        await channel.send(mention, embed=paginator.create_embed(), view=paginator)
        self.processed_spy_losses.add(victim["id"])


    @tasks.loop(seconds=SPY_MONITOR_CONFIG["check_interval"])
    async def monitor(self):
        try:
            check_time = datetime.now(timezone.utc)
            print(f"\n[ {check_time.strftime('%Y-%m-%d %H:%M:%S')} ] Running spy check...")
            
            guild = self.get_guild(SPY_MONITOR_CONFIG["guild_id"])
            channel = guild.get_channel(SPY_MONITOR_CONFIG["notification_channel_id"]) if guild else None
            if not channel:
                print("Error: Channel not found")
                return


            alliance_nations = await self.get_alliance_nations()
            if not alliance_nations:
                print("Warning: No alliance nations found")
                return


            new_spy_counts = {nation["id"]: nation.get("spies", 0) for nation in alliance_nations}


            for nation in alliance_nations:
                nation_id = nation["id"]
                current_spies = nation.get("spies", 0)
                previous_spies = self.nation_data.get(nation_id, {}).get("spies", current_spies)


                if (current_spies < previous_spies and 
                    nation_id not in self.processed_spy_losses and
                    current_spies == new_spy_counts.get(nation_id, current_spies)):
                    
                    print(f"New spy loss detected in {nation['nation_name']} (ID: {nation_id})")
                    
                    min_score = nation["score"] * SPY_MONITOR_CONFIG["score_range"][0]
                    max_score = nation["score"] * SPY_MONITOR_CONFIG["score_range"][1]
                    
                    potentials = await self.fetch_paginated_nations(min_score, max_score)
                    print(f"Found {len(potentials)} nations in score range {min_score:.2f}-{max_score:.2f}")
                    
                    attackers = [
                        a for a in potentials
                        if (self.was_active_at_exact_time(a.get("last_active"), check_time) and 
                           a.get("alliance", {}).get("id") not in SPY_MONITOR_CONFIG["alliance_ids"])
                    ]
                    print(f"Found {len(attackers)} nations active at check time")
                    
                    await self.send_alert(channel, nation, attackers, check_time)
                
                self.nation_data[nation_id] = {
                    "spies": current_spies,
                    "last_spies": previous_spies,
                    "last_checked": check_time
                }


            self.processed_spy_losses = {
                nation_id for nation_id in self.processed_spy_losses
                if nation_id in new_spy_counts and 
                   new_spy_counts[nation_id] <= self.nation_data.get(nation_id, {}).get("spies", 0)
            }


        except Exception as e:
            print(f"Critical error in monitor loop: {str(e)}")


    @monitor.before_loop
    async def before_monitor(self):
        await self.wait_until_ready()
        print("Bot is ready. Starting monitoring...")


async def send_paginated_results(interaction: discord.Interaction, targets: List[Dict], loot_percentage: float):
    if not targets:
        await interaction.followup.send("✗ No valid targets found to display", ephemeral=True)
        return


    total_pages = (len(targets) + RESULTS_PER_PAGE - 1) // RESULTS_PER_PAGE
    for page in range(total_pages):
        start_idx = page * RESULTS_PER_PAGE
        end_idx = start_idx + RESULTS_PER_PAGE
        page_targets = targets[start_idx:end_idx]


        embed = discord.Embed(
            title=f"🎯 Raid Targets Analysis \n(Page {page + 1}/{total_pages})\n",
            color=0xffffff,
            description="\n[Bot Guides Available Here](https://docs.google.com/document/d/1-MmLt-4HVKpvGT9-YVsqHoI_K6M25PV745iD3I1I3w8/edit?usp=drivesdk)\n\n▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬"
        )


        for idx, target in enumerate(page_targets, start_idx + 1):
            nation = target.get('nation', {})
            loot = target.get('loot', {})
            defense_rating = MilitaryAnalyzer.defense_rating(target.get('military', 0))
            alliance_name = target.get('alliance_name', 'None')
            alliance_rank = target.get('alliance_rank', 'N/A')


            field_content = [
                f"👑**Leader**: {nation.get('leader_name', 'Unknown')}",
                f"🌃**Cities**: {len(nation.get('cities', []))}",
                f"💯**Score**: {nation.get('score', 0):.2f}\n",
                f"💂**Soldiers**: {nation.get('soldiers', 0):,}",
                f"⚙️**Tanks**: {nation.get('tanks', 0):,}",
                f"🛩️**Aircraft**: {nation.get('aircraft', 0):,}",
                f"🚢**Ships**: {nation.get('ships', 0):,}\n",
                f"⚔️**Offensive Wars**: {nation.get('offensive_wars_count', 0)}",
                f"🛡️**Defensive Wars**: {nation.get('defensive_wars_count', 0)}\n",
                f"🏘️**Alliance**: {alliance_name} (Rank #{alliance_rank})\n",
                f"💰**Estimated Loot**: ${loot.get('total', 0) * loot_percentage:,.2f}\n"
            ]


            if nation.get('last_active'):
                try:
                    last_active_date = isoparse(nation['last_active']).astimezone(timezone.utc)
                    days_ago = (datetime.now(timezone.utc) - last_active_date).days
                    field_content.append(f"⏰**Last Active**: {last_active_date.strftime('%Y-%m-%d')} ({days_ago} days ago)\n")
                except Exception:
                    field_content.append("⏰**Last Active**: Unknown")


            if nation.get('id'):
                field_content.append(f"[Nation Link](https://politicsandwar.com/nation/id={nation['id']})")


            embed.add_field(
                name=f"{idx}.🏳️ {nation.get('nation_name', 'Unknown Nation')}",
                value="\n".join(field_content),
                inline=False
            )


            if idx < end_idx and idx < len(targets):
                embed.add_field(name=SEPARATOR, value="\u200b", inline=False)


        embed.set_footer(text=f"Operated by black_dragon | Page {page + 1}/{total_pages} |\n Do not attack:\n1) Top 35 alliance members\n2) Top 20 alliance applicants\n3) Allies and their allies")


        if page == 0:
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send(embed=embed)


def setup(bot: PnWBot):
    @bot.tree.command(name="raid", description="Find best raid targets with total loot (fetches 15000 nations)")
    @app_commands.describe(
        my_score="Your nation's current score",
        include_beige="Include beige nations (default: False)",
        pirate_policy="Whether to apply pirate policy bonus (required)",
        number_of_results="Number of results to display (1-50, default: 10)"
    )
    async def raid_command(
        interaction: discord.Interaction,
        my_score: float,
        pirate_policy: bool,
        include_beige: bool = False,
        number_of_results: int = 10
    ):
        try:
            if my_score <= 0:
                await interaction.response.send_message("✗ Nation score must be positive!", ephemeral=True)
                return


            if number_of_results < 1 or number_of_results > 50:
                await interaction.response.send_message("✗ Number of results must be between 1 and 50!", ephemeral=True)
                return


            await interaction.response.defer()
            finder = RaidTargetFinder()
            loading_msg = None


            try:
                loading_msg = await interaction.followup.send(f"📍 Fetching 15000 nations (analyzing top {number_of_results} targets)...")


                loot_percentage = WAR_DATA["base_loot_percentage"]
                if pirate_policy:
                    loot_percentage += WAR_DATA["pirate_bonus"]


                min_score = max(100, my_score * 0.75)
                max_score = my_score * 2.5


                nations, trade_prices = await finder.fetch_targets(min_score, max_score)
                if not include_beige:
                    nations = [n for n in nations if n.get('beige_turns', 0) == 0]


                analyzed = await finder.analyze_targets(nations, trade_prices, number_of_results)
                await finder.close()


                if not analyzed:
                    await interaction.followup.send("✗ No valid raid targets found in this range", ephemeral=True)
                    return


                if loading_msg:
                    try:
                        await loading_msg.delete()
                    except:
                        pass


                await send_paginated_results(interaction, analyzed, loot_percentage)


            except Exception as e:
                if loading_msg:
                    try:
                        await loading_msg.delete()
                    except:
                        pass
                logger.error(f"Error in raid command: {str(e)}", exc_info=True)
                await interaction.followup.send(f"✗ An error occurred: {str(e)}", ephemeral=True)
                await finder.close()


        except Exception as e:
            logger.error(f"Error in raid command setup: {str(e)}", exc_info=True)
            await interaction.followup.send(f"✗ An error occurred: {str(e)}", ephemeral=True)


    @bot.tree.command(name="loot", description="Check loot available from a specific nation")
    @app_commands.describe(nation_id="The ID of the nation to check")
    async def loot_command(interaction: discord.Interaction, nation_id: int):
        try:
            if nation_id <= 0:
                await interaction.response.send_message("✗ Nation ID must be positive!", ephemeral=True)
                return


            await interaction.response.defer()
            finder = RaidTargetFinder()
            
            try:
                data = await finder.fetch_nation(nation_id)
                nation_data = data.get('nations', {}).get('data', [])
                trade_prices = data.get('tradeprices', {}).get('data', [{}])[0]


                if not nation_data:
                    await interaction.followup.send("✗ No nation found with that ID", ephemeral=True)
                    return


                nation = nation_data[0]
                analyzed = await finder.analyze_nation(nation, trade_prices)
                await finder.close()


                embed = discord.Embed(
                    title=f"🛡️ Loot Analysis for {nation.get('nation_name', 'Unknown Nation')}",
                    color=0xffffff,
                    description="Detailed breakdown of loot available from this nation\n\n[Bot Guides Available Here](https://docs.google.com/document/d/1-MmLt-4HVKpvGT9-YVsqHoI_K6M25PV745iD3I1I3w8/edit?usp=drivesdk)\n\n▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬"
                )


                loot = analyzed.get('loot', {})
                defense_rating = MilitaryAnalyzer.defense_rating(analyzed.get('military', 0))


                embed.add_field(
                    name="📋 Nation Information",
                    value=(
                        f"👑**Leader**: {nation.get('leader_name', 'Unknown')}\n"
                        f"🌃**Cities**: {len(nation.get('cities', []))}\n"
                        f"💯**Score**: {nation.get('score', 0):.2f}\n"
                    ),
                    inline=False
                )


                embed.add_field(
                    name=" ",
                    value=(
                        f"💰**Total Loot Value**: ${loot.get('total', 0):,.2f}\n"
                        f"💵**Estimated Loot**: ${loot.get('total', 0) * WAR_DATA['base_loot_percentage']:,.2f}\n"
                    ),
                    inline=False
                )


                last_active_date = None
                if nation.get('last_active'):
                    try:
                        last_active_date = isoparse(nation['last_active']).astimezone(timezone.utc)
                    except Exception as e:
                        logger.error(f"Error parsing last_active: {str(e)}")


                activity_info = []
                if last_active_date:
                    now = datetime.now(timezone.utc)
                    delta = now - last_active_date
                    days_ago = delta.days
                    activity_info.extend([
                        f"⏰**Last Active**: {last_active_date.strftime('%Y-%m-%d')}",
                        f"⏱️**({days_ago} days ago)**"
                    ])
                else:
                    activity_info.append("**Last Active**: Unknown")


                embed.add_field(
                    name=" ",
                    value="\n".join(activity_info),
                    inline=False
                )


                nation_id = nation.get('id')
                if nation_id:
                    embed.add_field(
                        name=" ",
                        value=f"[View Nation](https://politicsandwar.com/nation/id={nation_id})",
                        inline=False
                    )


                embed.set_footer(text="Operated by black_dragon, Contact Him in Case of Errors.\nAlso, Do not attack:\n1) Members of the top 35 alliances\n2) Applicants of the top 20 alliances\n3) Allies and their allies")


                await interaction.followup.send(embed=embed)


            except Exception as e:
                await finder.close()
                logger.error(f"Error in loot command: {str(e)}", exc_info=True)
                await interaction.followup.send(f"✗ An error occurred: {str(e)}", ephemeral=True)


        except Exception as e:
            logger.error(f"Error in loot command setup: {str(e)}", exc_info=True)
            await interaction.followup.send(f"✗ An error occurred: {str(e)}", ephemeral=True)


    @bot.tree.command(name="who", description="Get detailed information about a specific nation")
    @app_commands.describe(nation_id="The ID of the nation to look up")
    async def who_command(interaction: discord.Interaction, nation_id: int):
        try:
            if nation_id <= 0:
                await interaction.response.send_message("✗ Nation ID must be positive!", ephemeral=True)
                return


            await interaction.response.defer()
            finder = RaidTargetFinder()
            
            try:
                data = await finder.fetch_nation(nation_id)
                nation_data = data.get('nations', {}).get('data', [])
                trade_prices = data.get('tradeprices', {}).get('data', [{}])[0]


                if not nation_data:
                    await interaction.followup.send("✗ No nation found with that ID", ephemeral=True)
                    return


                nation = nation_data[0]
                alliance_data = await finder.fetch_targets_batch(100, 999999, 100, 1)
                finder.alliance_rankings = {
                    a['id']: idx + 1
                    for idx, a in enumerate(alliance_data.get('alliances', {}).get('data', []))
                }


                analyzed = await finder.analyze_nation(nation, trade_prices)
                await finder.close()


                embed = discord.Embed(
                    title=f"🛡️ Nation Details: {nation.get('nation_name', 'Unknown Nation')}",
                    color=0xffffff,
                    description="\n[Bot Guides Available Here](https://docs.google.com/document/d/1-MmLt-4HVKpvGT9-YVsqHoI_K6M25PV745iD3I1I3w8/edit?usp=drivesdk)\n\n▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬"
                )


                loot = analyzed.get('loot', {})
                defense_rating = MilitaryAnalyzer.defense_rating(analyzed.get('military', 0))
                alliance_name = analyzed.get('alliance_name', 'None')
                alliance_rank = analyzed.get('alliance_rank', 'N/A')


                basic_info = [
                    f"👑**Leader**: {nation.get('leader_name', 'Unknown')}",
                    f"🌃**Cities**: {len(nation.get('cities', []))}",
                    f"💯**Score**: {nation.get('score', 0):.2f}\n"
                ]


                military_forces = [
                    f"💂**Soldiers**: {nation.get('soldiers', 0):,}",
                    f"⚙️**Tanks**: {nation.get('tanks', 0):,}",
                    f"🛩️**Aircraft**: {nation.get('aircraft', 0):,}",
                    f"🚢**Ships**: {nation.get('ships', 0):,}",
                    f"🚀**Missiles**: {nation.get('missiles', 0):,}",
                    f"☢️**Nukes**: {nation.get('nukes', 0):,}",
                    f"🕵️**Spies**: {nation.get('spies', 0):,}\n"
                ]


                war_status = [
                    f"⚔️**Offensive Wars**: {nation.get('offensive_wars_count', 0)}",
                    f"🛡️**Defensive Wars**: {nation.get('defensive_wars_count', 0)}",
                    f"🟡**Beige Turns**: {nation.get('beige_turns', 0)}",
                    f"⛱️**Vacation Mode**: {'Yes' if nation.get('vacation_mode_turns', 0) > 0 else 'No'}\n"
                ]


                alliance_info = [
                    f"🏘️**Alliance**: {alliance_name}",
                    f"**Rank**: #{alliance_rank if alliance_rank != 'N/A' else 'N/A'}\n",
                    f"💰**Estimated Loot**: ${loot.get('total', 0) * WAR_DATA['base_loot_percentage']:,.2f}\n"
                ]


                last_active_date = None
                if nation.get('last_active'):
                    try:
                        last_active_date = isoparse(nation['last_active']).astimezone(timezone.utc)
                    except Exception as e:
                        logger.error(f"Error parsing last_active: {str(e)}")


                activity_info = []
                if last_active_date:
                    now = datetime.now(timezone.utc)
                    delta = now - last_active_date
                    days_ago = delta.days
                    activity_info.extend([
                        f"⏰**Last Active**: {last_active_date.strftime('%Y-%m-%d')}",
                        f"⏱️**({days_ago} days ago)**\n"
                    ])
                else:
                    activity_info.append("**Last Active**: Unknown")


                nation_id = nation.get('id')
                link_info = [
                    f"[Nation Link](https://politicsandwar.com/nation/id={nation_id})" if nation_id else "Link: N/A"
                ]


                field_content = [
                    "\n".join(basic_info),
                    "\n".join(military_forces),
                    "\n".join(war_status),
                    "\n".join(alliance_info),
                    "\n".join(activity_info),
                    "\n".join(link_info)
                ]


                embed.add_field(
                    name=f"📋 {nation.get('nation_name','Unknown Nation')}",
                    value="\n".join(field_content),
                    inline=False
                )


                embed.set_footer(text="Operated by black_dragon, Contact Him in Case of Errors. \nAlso, Do not attack:\n1) Members of the top 35 alliances\n2) Applicants of the top 20 alliances\n3) Allies and their allies")


                await interaction.followup.send(embed=embed)


            except Exception as e:
                await finder.close()
                logger.error(f"Error in who command: {str(e)}", exc_info=True)
                await interaction.followup.send(f"✗ An error occurred: {str(e)}", ephemeral=True)


        except Exception as e:
            logger.error(f"Error in who command setup: {str(e)}", exc_info=True)
            await interaction.followup.send(f"✗ An error occurred: {str(e)}", ephemeral=True)


    @bot.event
    async def on_ready():
        logger.info(f"Logged in as {bot.user.name} ({bot.user.id})")
        try:
            await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="for /raid, /loot and /who commands"))
            synced = await bot.tree.sync()
            logger.info(f"Synced {len(synced)} slash commands")
        except Exception as e:
            logger.error(f"Error during startup: {str(e)}")


if __name__ == "__main__":
    bot = PnWBot()
    setup(bot)
    try:
        bot.run(DISCORD_TOKEN)
    except Exception as e:
        logger.critical(f"Failed to start bot: {str(e)}")

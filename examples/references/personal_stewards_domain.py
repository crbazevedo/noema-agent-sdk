"""Distinct synthetic situation classes; integer-BRL scenario arithmetic, not advice."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Assessment:
    known: list
    uncertain: list
    recommendation: str
    options: list
    ready: bool
    evidence_ids: list


class SituationDomain:
    numeric_fields = ()
    boolean_fields = ()
    text_fields = ()

    def validate_values(self, values, uncertain):
        return []

    def assess(self, state):
        values, known, uncertain, evidence = {}, [], [], []
        for key, claims in state["sources"].items():
            current = [
                c
                for c in claims.values()
                if type(c.get("observed_at")) is int
                and type(c.get("valid_until")) is int
                and c["observed_at"] <= state["now"] <= c["valid_until"]
            ]
            if not current:
                uncertain.append(f"{key}: source expired or future-dated; refresh required")
                continue
            evidence.extend(c["event_id"] for c in current)
            if len({repr(c["value"]) for c in current}) > 1:
                uncertain.append(f"{key}: conflicting independent sources; unresolved")
            else:
                values[key] = current[0]["value"]
        for key in self.numeric_fields:
            if key in values and (type(values[key]) is not int or not 0 <= values[key] <= 10**9):
                values.pop(key)
                uncertain.append(
                    f"{key}: unsupported amount/count; require bounded nonnegative integer"
                )
        for key in self.boolean_fields:
            if key in values and type(values[key]) is not bool:
                values.pop(key)
                uncertain.append(f"{key}: unsupported boolean evidence")
        for key in self.text_fields:
            if key in values and (
                not isinstance(values[key], str)
                or not values[key].strip()
                or len(values[key]) > 512
            ):
                values.pop(key)
                uncertain.append(f"{key}: require bounded nonempty text")
        semantic_missing = self.validate_values(values, uncertain)
        known = [f"{key}: {value}" for key, value in values.items()]
        missing = [key for key in self.required if key not in values] + semantic_missing
        uncertain.extend(f"{key}: required current evidence missing" for key in missing)
        rec, options, gaps = self.compare(values)
        if missing:
            rec = "Abstain from a current recommendation; refresh: " + ", ".join(missing)
            options = [
                {
                    "id": "refresh",
                    "label": "Obtain current required evidence",
                    "admissible": True,
                    "tradeoff": "Delays the review; avoids stale advice",
                }
            ]
        return Assessment(known, uncertain + gaps, rec, options, not missing, sorted(set(evidence)))


class FinancialSteward(SituationDomain):
    id = "finance"
    title = "Maya's liquid-reserve and bond-maturity review"
    goal = "Prepare an evidence-backed liquidity review for a human decision"
    stakes = "Uncertain bonus, possible family costs, rent goal, concentrated employer equity"
    required = ("salary", "expenses", "liquid_cash", "bond_maturity", "family_buffer")
    numeric_fields = (*required, "rent", "moving_cost")
    inquiry = {"rent_alternatives": [3800, 4100], "moving_cost": 6000}

    def validate_values(self, values, uncertain):
        if "rent_alternatives" in values:
            alternatives = values["rent_alternatives"]
            if (
                not isinstance(alternatives, list)
                or not 1 <= len(alternatives) <= 100
                or any(type(x) is not int or not 0 <= x <= 10**9 for x in alternatives)
            ):
                values.pop("rent_alternatives")
                uncertain.append(
                    "rent_alternatives: require 1–100 bounded nonnegative integer rents"
                )
        return []

    def compare(self, v):
        expenses, cash = v.get("expenses", 0), v.get("liquid_cash", 0)
        reserve = expenses * 6 + v.get("family_buffer", 0)
        shortfall = max(0, reserve - cash)
        options = [
            {
                "id": "liquidity",
                "label": "Review liquid reserve before reinvestment",
                "reserve_target_brl": reserve,
                "cash_gap_brl": shortfall,
                "maturity_brl": v.get("bond_maturity", 0),
                "units": "BRL; salary/expenses/rent monthly; cash and maturity are stocks/inflows",
                "maturity_condition": (
                    "Future net proceeds, conditional; not income or current cash"
                ),
                "maturity_receipt_verified": False,
                "unfunded_after_maturity_brl": max(0, shortfall - v.get("bond_maturity", 0)),
                "tradeoff": "Preserves flexibility; yield not estimated",
                "admissible": True,
            },
            {
                "id": "rent",
                "label": "Compare lower-rent options",
                "monthly_salary_surplus_brl": v.get("salary", 0) - expenses,
                "tradeoff": "Moving cost and suitability need human review",
                "admissible": True,
            },
            {
                "id": "reinvest",
                "label": "Defer instrument-specific reinvestment choice",
                "tradeoff": "Rates, inflation, taxes, suitability and terms need current review",
                "admissible": False,
                "reason": "No transaction capability or investment mandate",
            },
        ]
        if v.get("rent_alternatives") and "rent" in v:
            savings = v["rent"] - min(v["rent_alternatives"])
            options[1]["potential_monthly_saving_brl"] = savings
            if savings > 0 and "moving_cost" in v:
                options[1]["break_even_months_rounded_up"] = (
                    v["moving_cost"] + savings - 1
                ) // savings
        return (
            f"Review a R${reserve:,} scenario reserve; confirmed cash gap R${shortfall:,}.",
            options,
            [
                "Six expense-months plus family buffer is a fixture preference, not advice.",
                "Bonus and possible child costs are scenarios, not guaranteed income or plans.",
                "Employer equity is concentrated and illiquid; excluded from spendable reserve.",
                "Rate/inflation expectations are claims, not predicted returns or success odds.",
            ],
        )


class ResearchSteward(SituationDomain):
    id = "research"
    title = "Lina and Omar's pilot-study decision brief"
    goal = "Prepare a collaborator-reviewed pilot-study checkpoint before a deadline"
    stakes = (
        "Small sample, disputed effect direction, collaborator availability, incomplete evidence"
    )
    required = ("sample_size", "deadline", "collaborator_available", "protocol")
    numeric_fields = ("sample_size",)
    boolean_fields = ("collaborator_available",)
    text_fields = ("deadline", "protocol")
    inquiry = {"missingness_review": "3 of 12 paired measurements missing; do not impute silently"}

    def compare(self, v):
        return (
            "Label the pilot inconclusive; prepare an evidence-gap brief and ask the collaborator "
            "to choose replication or a narrower deadline deliverable.",
            [
                {
                    "id": "gap_brief",
                    "label": "Prepare an evidence-gap brief for review",
                    "admissible": True,
                    "tradeoff": "Meets checkpoint; establishes no research claim",
                },
                {
                    "id": "replication",
                    "label": "Plan replication with collaborator",
                    "admissible": v.get("collaborator_available", False),
                    "tradeoff": "Needs availability and protocol agreement; extends timeline",
                },
                {
                    "id": "claim",
                    "label": "Assert a positive finding",
                    "admissible": False,
                    "reason": "Conflicting/incomplete pilot evidence cannot establish a result",
                },
            ],
            [
                "Disputed effect direction; no significance or publication claim inferred.",
                "A reviewed brief closes only this checkpoint, not the study or replication.",
            ],
        )


class GatheringSteward(SituationDomain):
    id = "gathering"
    title = "Eight friends' accessible Saturday gathering"
    goal = "Prepare a feasible gathering plan and unsent invitation for human review"
    stakes = "Eight adults, R$600 ceiling, accessibility, rain, changing venue deadline"
    required = (
        "budget",
        "adults",
        "rain",
        "venue_quote",
        "accessible",
        "available",
        "time",
        "park_accessible",
        "guest_available_time",
    )
    numeric_fields = ("budget", "adults", "venue_quote")
    boolean_fields = ("rain", "accessible", "available", "park_accessible")
    text_fields = ("time", "guest_available_time")
    inquiry = {
        "guest_schedule_check": "Eight synthetic adults free Saturday 15:00–18:00",
        "guest_available_time": "Saturday 15:00–18:00",
    }

    def validate_values(self, values, uncertain):
        missing = []
        if "adults" in values and not 1 <= values["adults"] <= 1000:
            values.pop("adults")
            uncertain.append("adults: require 1–1000 adults for this per-person-cost model")
        if values.get("time") != values.get("guest_available_time"):
            missing.append("guest_availability_for_current_time")
            uncertain.append("Guest availability does not establish the current proposed time")
        return missing

    def compare(self, v):
        indoor = (
            v.get("available") is True
            and v.get("accessible") is True
            and 0 < v.get("venue_quote", 0) <= v.get("budget", 0)
        )
        park_cost = 15 * v.get("adults", 0)
        outdoor = (
            v.get("rain") is False
            and v.get("park_accessible") is True
            and "budget" in v
            and 0 < park_cost <= v["budget"]
        )
        if v.get("time") != v.get("guest_available_time"):
            indoor = outdoor = False
        rec = (
            "Prepare the accessible indoor plan."
            if indoor
            else (
                "Prepare a weather-dependent park alternative."
                if outdoor
                else "No feasible current venue; discuss postponement without booking."
            )
        )
        return (
            rec,
            [
                {
                    "id": "park",
                    "label": "Park",
                    "cost_brl": park_cost,
                    "admissible": outdoor,
                    "tradeoff": "Lower cost, weather-dependent",
                    "reason": "Needs dry weather, park access, current guest time and budget",
                },
                {
                    "id": "indoor",
                    "label": "Accessible indoor room",
                    "cost_brl": v.get("venue_quote"),
                    "admissible": indoor,
                    "tradeoff": "Higher cost; no booking authorized",
                    "reason": "Requires current availability, accessibility and budget compliance",
                },
                {
                    "id": "postpone",
                    "label": "Discuss postponement",
                    "admissible": True,
                    "tradeoff": "Preserves constraints but loses the chosen date",
                },
            ],
            ["Availability can expire; no reservation, payment or invitation is sent."],
        )


DOMAINS = {d.id: d for d in (FinancialSteward(), ResearchSteward(), GatheringSteward())}


def initial_facts(domain):
    return {
        "finance": {
            "salary": 14500,
            "expenses": 9200,
            "liquid_cash": 42000,
            "bond_maturity": 18000,
            "family_buffer": 12000,
            "rent": 4800,
            "bonus": "0–24000, uncertain",
            "employer_equity": "R$210000 illiquid",
            "inflation_expectation": "4.2%, synthetic source",
            "rate_expectation": "falling",
        },
        "research": {
            "sample_size": 12,
            "deadline": "Friday 16:00",
            "protocol": "paired pilot v1",
            "collaborator_available": True,
            "effect_direction": "positive",
        },
        "gathering": {
            "budget": 600,
            "park_accessible": True,
            "guest_available_time": "Saturday 15:00–18:00",
            "adults": 8,
            "rain": False,
            "venue_quote": 480,
            "accessible": True,
            "available": False,
            "time": "Saturday 15:00–18:00",
        },
    }[domain]


def public_scenarios():
    def observe(facts, **kw):
        return {"op": "observe", "facts": facts, **kw}

    end = [{"op": "wake"}, {"op": "approve"}, {"op": "wake"}]
    return [
        {
            "name": "P1-financial-steward",
            "domain": "finance",
            "commands": [
                {"op": "wake"},
                {"op": "wake"},
                observe(
                    {
                        "bonus": "0, payout delayed",
                        "rate_expectation": "higher for longer",
                        "family_buffer": 18000,
                    },
                    due=12,
                    why="Bonus delay and family-cost scenario changed",
                ),
                observe(
                    {"inflation_expectation": "5.1%, conflicting synthetic source"},
                    source="research-note",
                ),
                {"op": "wake"},
                {"op": "restart"},
                *end,
            ],
        },
        {
            "name": "P2-research-collaboration",
            "domain": "research",
            "commands": [
                {"op": "wake"},
                observe(
                    {"effect_direction": "negative"},
                    source="collaborator-reanalysis",
                    due=12,
                    why="Independent reanalysis disputes direction before checkpoint",
                ),
                observe(
                    {"collaborator_available": False},
                    due=10,
                    why="Collaborator can review only async",
                ),
                {"op": "wake"},
                *end,
            ],
        },
        {
            "name": "P3-gathering-rain-accessibility",
            "domain": "gathering",
            "commands": [
                {"op": "wake"},
                {"op": "wake"},
                observe(
                    {"rain": True, "accessible": False, "available": True},
                    due=12,
                    why="Rain and stairs invalidate first venue; deadline moved earlier",
                ),
                {"op": "wake"},
                {"op": "wake"},
                observe(
                    {"venue_quote": 560, "accessible": True, "available": True},
                    due=25,
                    why="New ground-floor room available until its own later deadline",
                ),
                {"op": "wake"},
                *end,
            ],
        },
        {
            "name": "P4-finance-revoked",
            "domain": "finance",
            "commands": [{"op": "wake"}, {"op": "revoke"}, {"op": "wake"}],
        },
        {
            "name": "P5-research-stale",
            "domain": "research",
            "commands": [{"op": "wake"}, {"op": "advance", "minutes": 121}, {"op": "wake"}],
        },
        {
            "name": "P6-gathering-interrupted",
            "domain": "gathering",
            "commands": [
                {"op": "wake"},
                {"op": "wake"},
                {"op": "approve"},
                observe({"time": "Saturday 17:00–20:00"}, why="Host changed time after approval"),
                {"op": "restart"},
                {"op": "wake"},
                {"op": "wake"},
            ],
        },
        {
            "name": "P7-finance-race",
            "domain": "finance",
            "commands": [{"op": "wake"}, {"op": "wake", "before_effect": {"salary": 11000}}],
        },
    ]

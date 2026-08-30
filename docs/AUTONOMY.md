# Autonomy model

## Autonomy is runtime independence, not absence of governance

A fully autonomous Noema agent can continue operating without new human prompts. It can observe, self-trigger, deliberate, prioritize, execute, retry, compensate, and reflect.

Its authority is still explicit.

## Authority levels

```text
OBSERVE
PROPOSE
ACT_REVERSIBLE
ACT_IRREVERSIBLE
ADMINISTER
```

The effective authority required by an action is the maximum of:

- the action intent's declared requirement;
- the capability's declared requirement.

## Risk levels

```text
NEGLIGIBLE
LOW
MEDIUM
HIGH
CRITICAL
```

The effective risk is likewise conservative: the maximum declared by the action and capability.

## Authorization gates

The built-in policy checks:

- authority ceiling;
- risk ceiling;
- irreversible-action permission;
- confidence threshold;
- attention limit;
- falsifier requirement for consequential actions;
- deployment-specific deny rules.

## Dynamic delegation

`TrustLedger` uses a beta-distribution estimate rather than a permanent scalar reputation. Authority recommendations use a conservative uncertainty-adjusted bound.

This design enforces two distinctions:

```text
reliability of actor ≠ truth of proposition
past failure ≠ permanent exclusion
```

A low-trust actor may still provide correct evidence. A high-trust actor may still be wrong.

## Sovereign mode

`AutonomyProfile.sovereign()` removes mandatory human approval ceilings. It is useful for controlled environments, simulations, local sandboxes, and explicitly delegated production domains.

Sovereign mode does not bypass:

- event traces;
- capability typing;
- causal linkage;
- custom policy rules;
- environment-level permissions;
- operating-system or infrastructure controls.

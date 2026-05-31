# SEBI Peak Margin Framework for Derivatives and Cash Segments

**Circular Reference:** SEBI/HO/MRD/DRMNP/CIR/P/2020/220
**Date:** November 2, 2020 (phased implementation; fully effective September 1, 2021)
**Updated by:** SEBI/HO/MRD/DOP/P/CIR/2022/0076 (April 25, 2022)
**Issued By:** Securities and Exchange Board of India (SEBI)
**Applicable To:** All Stock Brokers, Stock Exchanges, Clearing Corporations, Depositories

---

## 1. Introduction and Rationale

Prior to the introduction of the Peak Margin framework, the margin collection system in Indian securities markets permitted stock brokers to collect margins from clients at the end of the trading day, based on the closing positions. This created a significant systemic risk: intraday positions that were far larger than the client's financial capacity could be taken during the day, with brokers using funds from other clients or their own capital to fund intraday obligations. Such practices led to situations where brokers, facing large intraday losses, were unable to settle obligations at end of day, thereby threatening the stability of the entire market infrastructure.

The Peak Margin framework was introduced to mandate that brokers collect margin from clients upfront, before placing trades, based on the maximum or "peak" margin exposure at any point during the day. This ensures that clients only take on positions commensurate with the margin they have already deposited.

---

## 2. Key Provisions of the Peak Margin Framework

### 2.1 Upfront Margin Collection

With effect from September 1, 2021, stock brokers are required to collect the full applicable margin from clients before placing any order. The applicable margin includes:

- **SPAN Margin (Standard Portfolio Analysis of Risk):** Computed by clearing corporations based on option pricing models to cover the largest potential loss on a portfolio over a one-day period.
- **Exposure Margin:** An additional margin levied over SPAN to cover residual risk, typically 3% for index derivatives and 5% for stock derivatives.
- **Extreme Loss Margin (ELM):** Applied to the cash segment on a Value at Risk basis to cover losses in extreme market conditions.
- **VaR Margin:** Applied to all securities in the cash segment based on statistical volatility of the security's price.

### 2.2 Peak Margin Reporting

Clearing corporations perform intraday snapshots of client positions at random intervals (minimum 4 times per day). The maximum margin obligation across all snapshots is the "peak margin." Brokers are required to ensure that the margin collected from clients at the time of the snapshot is at least equal to the peak margin obligation.

If a broker fails to collect peak margin from clients, the shortfall is reported by the clearing corporation to SEBI. The broker is penalised as follows:

- Margin shortfall of less than Rs. 1 lakh or less than 10% of applicable margin: Penalty of 0.5% per day of shortfall
- Margin shortfall between Rs. 1 lakh and Rs. 1 crore or between 10%-50% of applicable margin: Penalty of 1.0% per day
- Margin shortfall above Rs. 1 crore or above 50% of applicable margin: Penalty of 5.0% per day

Penalties exceeding Rs. 1 crore per day may result in trading restrictions imposed by the exchange.

### 2.3 Prohibition on Funding Intraday Positions

Brokers must not provide any form of funding or leverage to clients beyond the amount of margin deposited by the client. This means:

- Brokers cannot allow clients to take positions that exceed their deposited margin.
- Brokers cannot use funds or securities of one client to fund positions of another client.
- Intraday leveraged positions ("margin intraday square off" or "MIS" orders) are only permitted if the broker collects the required upfront margin at the time of order placement.
- Product types that offer higher leverage than permitted by the SPAN+Exposure margin framework are not permitted.

### 2.4 Consequences for Margin Shortfall

When a client's account shows a margin shortfall at end of day (i.e., the margin deposited by the client is less than the margin required for open positions), the broker is required to take the following steps in order:

1. Immediately notify the client of the margin shortfall.
2. Give the client one trading day to deposit additional margin.
3. If the client fails to deposit additional margin within the prescribed time, the broker must compulsorily square off the client's open positions to bring the margin obligation to zero or within the client's available margin.
4. The broker must not carry forward any positions for which full margin has not been received.

### 2.5 Upfront Margin for Cash Segment — Delivery Trades

For equity delivery trades (trades intended to result in actual delivery of securities), the following margins apply:

- VaR margin computed daily by the exchange clearing corporation based on the 99th percentile of daily price movements over the preceding 6 months.
- ELM at 1.5 times the VaR margin for stocks in Group I (liquid stocks) and 3.5 times VaR for stocks in Group II and III.
- Additional surveillance margins may be applied by exchanges at their discretion based on price volatility, abnormal trading volumes, or circuit breaker triggers.

Brokers must collect these margins upfront before accepting delivery buy orders from clients.

---

## 3. Treatment of Client Collateral

### 3.1 Acceptable Forms of Margin

The following forms of collateral are acceptable as margin:

- **Cash:** Deposited in designated client bank accounts and reported to clearing corporations.
- **Fixed Deposits:** Issued by Scheduled Commercial Banks in the name of clearing corporations as beneficiary.
- **Treasury Bills and Government Securities:** At applicable haircuts.
- **Approved Equity Shares:** Subject to concentration limits and applicable haircuts (15%–100% depending on the stock's group classification).
- **Approved Mutual Fund Units:** Subject to haircuts as specified by clearing corporations.

### 3.2 Client Collateral Pledge Mechanism (DDPI and SEBI Margin Pledge)

With effect from September 1, 2020, brokers must use the margin pledge mechanism to utilise client securities as collateral. The process involves:

- Clients pledging securities directly in their demat accounts in favour of the clearing corporation through the NSDL/CDSL pledge mechanism.
- Brokers cannot hold client securities in their own pool accounts for margin purposes; all securities used as collateral must be pledged through the exchange-designated mechanism.
- The re-pledge by clearing members to clearing corporations is permitted only for the purpose of meeting margin obligations.
- Any unpledge of client securities must be done on the same day after close of trading if positions are squared off.

### 3.3 Restrictions on Use of Client Collateral

Brokers are strictly prohibited from:

- Transferring client collateral to their own proprietary accounts.
- Using client collateral for any purpose other than margin obligations for that specific client.
- Pooling client collateral in a manner that allows cross-use between clients.
- Hypothecating, re-pledging (except to clearing corporations), or otherwise dealing with client collateral without explicit written consent.

---

## 4. Intraday Margin Calls and Square-Off Procedures

### 4.1 Intraday Margin Calls

If, during the trading day, the value of a client's positions increases such that the required margin exceeds the deposited margin (due to adverse price movements), the broker must issue a real-time intraday margin call to the client. The broker's risk management systems (RMS) must be configured to:

- Monitor client positions and margin levels on a real-time basis.
- Send automated alerts when margin utilisation reaches 80% of available margin.
- Initiate auto square-off of positions when margin utilisation reaches 90% unless the client immediately deposits additional margin.

### 4.2 Auto Square-Off Policy

Each broker must have a documented auto square-off policy that:

- Specifies the threshold at which auto square-off will be triggered (typically 90% margin utilisation or a breach of exchange-imposed position limits).
- Is disclosed to clients at the time of account opening and reiterated in the risk disclosure document.
- Is executed without any requirement for client consent at the time of square-off (since the policy is pre-consented at account opening).
- Provides for the broker to square off positions in a manner that minimises market impact while prioritising risk reduction.

---

## 5. Reporting Requirements

### 5.1 Daily Margin Reporting to Exchanges

Brokers must submit daily reports to exchanges and clearing corporations containing:

- Client-wise opening and closing margin requirements.
- Margin collected from each client (cash and collateral separately).
- Margin shortfall, if any, at end of day.
- Details of positions squared off due to margin shortfall.

### 5.2 Monthly Compliance Certificate

Brokers must submit a monthly compliance certificate to the exchange confirming that:

- Margins have been collected upfront from all clients for all segments.
- No client's margin has been used for another client's obligations.
- Client funds have been segregated from broker's own funds at all times.
- No leveraged products beyond SEBI-permitted limits have been offered to clients.

---

## 6. Penalties and Enforcement

Non-compliance with peak margin requirements has been a priority area for SEBI enforcement since FY2022. Brokers found guilty of:

- Repeatedly failing to collect upfront margins: Suspension of proprietary trading for 30 days and direction to refund clients any losses attributable to the margin default.
- Diverting or improperly applying client funds or collateral for non-client purposes: Suspension or cancellation of registration and criminal referral under Section 24 of the SEBI Act, 1992.
- Providing undisclosed leverage: Disgorgement of profits and monetary penalty up to Rs. 25 crores.

SEBI has conducted thematic inspections of stock brokers focused on peak margin compliance, and several brokers have been penalised in public orders available on SEBI's website.

---

## 7. Conclusion

The Peak Margin framework represents a fundamental shift in the margin collection paradigm in Indian securities markets. By requiring upfront collection of the full applicable margin, SEBI has substantially reduced the risk of broker defaults arising from client position losses exceeding collected margins. This framework protects not just individual clients but the integrity of the broader market by ensuring that clearing corporations can always rely on collected margins to cover settlement obligations.

---

*Securities and Exchange Board of India*
*Mumbai, India*

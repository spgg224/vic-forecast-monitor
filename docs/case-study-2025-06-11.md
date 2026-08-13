# Case study: a forecast spike that unwound before dispatch

## Selection rule

This event was selected mechanically as the largest absolute VIC1 price error in 2025 using the P5MIN vintage nearest to a 30-minute forecast horizon. It was not chosen after visually searching for a convenient story.

## What the public forecast showed

For the interval ending **8:05 am NEM time on 11 June 2025**:

- the 59-minute forecast was **$16,052.27/MWh**;
- the forecast rose to **$17,499.65/MWh** around 34 minutes before the interval;
- the declared 30-minute vintage was **$16,961.09/MWh**;
- by roughly 14 minutes out, it had fallen to **$3,882.89/MWh**;
- by roughly 9 minutes out, it was **$900.00/MWh**;
- by roughly 4 minutes out, it was **$224.13/MWh**; and
- the realised VIC1 price was **$228.64/MWh**.

The 30-minute error was therefore an over-forecast of **$16,732.46/MWh**, while the final short-horizon forecast was close to the realised result.

## Why it matters

Looking only at the final forecast would hide a large change in market expectations during the preceding hour. Looking only at the 30-minute miss would hide the fact that the forecast corrected sharply before dispatch. The event demonstrates why forecast issue time, target time and forecast horizon must remain separate in any honest historical analysis.

## What this analysis does not claim

The regional price series alone does not establish why the projected spike disappeared. Explaining the mechanism requires timestamped constraint, interconnector, generator-availability and dispatch information. Until those records are added, the dashboard reports the forecast evolution without asserting a cause.


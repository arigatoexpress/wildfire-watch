---
to: Fire Chief, Crested Butte Fire Protection District (TBD — confirm name; CBFPD admin (970) 349-5333; 700 6th Street, Crested Butte, CO 81224)
subject: Crested Butte resident, drone test polygon over the Slate River drainage — 30 minutes at the station?
priority: high
intent: loa-request
gated_on: Part 107 certificate (study underway, test booked); LAANC pre-auth for KGUC class E; signed Letter of Authorization from CBFPD before any flight
---

Chief TBD,

I live in the valley and I am building a small autonomous-drone project that I would like your read on before I do anything in your district. I am writing to ask for thirty minutes at your station, on your schedule, to walk you through it and see whether a tightly bounded test polygon over the Slate River drainage west of Mt. Crested Butte is something CBFPD would consider authorizing later this summer.

The short version. The project is called wildfire-watch. The premise is that the first 30 minutes of an ignition decide whether it stays under an acre or becomes a Marshall Fire. ALERTCalifornia's mountain-camera network and the GOES/VIIRS satellites are real, and they help, but both have documented blind spots in canyon and wildland-urban-interface terrain — exactly what we have here. The wedge I am working on is a small civilian patrol layer, hardware already in hand (a DJI Mavic Mini, a Mac mini, two Raspberry Pis), that can be flown manually first and that produces a structured fire-signal data stream a fire chief, GMUG, or the state DFPC could read.

I have already drawn up the Slate River drainage polygon (~1 km², below Mt. Crested Butte, accessible from the gondola road, beetle-killed timber stands above the river) and the corresponding mission file, the AOR brief covering KGUC class E, the West Elk Wilderness no-fly boundary, and the high-altitude derating math. Nothing flies until I have my Part 107 (studying now, test booked), LAANC pre-auth at KGUC, and a Letter of Authorization signed by your office. I am not asking you to authorize a flight today. I am asking for thirty minutes to show you the simulator and the AOR plan, so that when I do come back with the LOA paperwork in a few weeks, you have already seen what you would be authorizing.

Two specific things I would like your input on, if your time allows.

First, beetle-kill ground truth. The Colorado State Forest Service publishes beetle-kill polygons at a coarse cadence; CBFPD almost certainly has a working sense of where the worst standing-dead stands are above the Slate River that doesn't show up on any public map. Even an informal pointer to "start here, not there" would dramatically improve where I propose to fly first.

Second, escalation. The system can emit alerts in TAK / Cursor-on-Target XML — the same format ATAK runs on. If your incident commanders use ATAK or are open to it, integrating wildfire-watch alerts into a tablet you already use is straightforward. If not, a plain phone call from me (the human operator) when an alert fires is the fallback. I want to match your existing workflow, not add a new one.

There is no commercial ask in this email. I am building the project as research and as a Colorado-resident contribution to the valley's fire posture. The repo is open source under Apache-2.0 and is at https://github.com/arigatoexpress/wildfire-watch.

Would the second or third week of June work for thirty minutes? I am flexible on day and time. Happy to come to the station on 6th Street, or to meet at the County FPD coordination office in Gunnison if that is easier.

Thank you for the work you and the district do. No rush on this — if June is full, July is fine.

— TBD (operator name)
TBD (operator phone)
aristotlespec@gmail.com
https://github.com/arigatoexpress/wildfire-watch

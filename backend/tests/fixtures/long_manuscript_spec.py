"""
Stage 12.1 (PA-C6 / PA-H12; the A13 follow-up) — a realistic long manuscript
with PLANTED evidence, for measuring Plot Assistant ranking objectively.

"The Saltmarsh Ledger": 40 chapters. The scene prose of each chapter is written
by the model from the beats below (tests/fixtures/build_long_manuscript.py, run
once; the result is committed as long_manuscript_pa.json so measurements are
reproducible without regenerating). The PLANTED paragraphs are inserted
verbatim at fixed chapters by that script, so the ground truth is exact:

  * each scenario has ONE plot-critical paragraph that answers its question,
    and 2–3 keyword-heavy DECOY paragraphs in other chapters that share the
    question's vocabulary but are incidental (PA-C6: context prioritisation);
  * two scenarios ask for a character's most important act, where that
    character has many minor appearances and one major revelation (PA-H12:
    plot importance).

Every planted paragraph carries a unique `key` sentence fragment so the
measurement can tell which retrieved chunk contains it.
"""

TITLE = "The Saltmarsh Ledger"
GENRE = "historical mystery"

CHARACTERS = [
    ("Wren Halloway", "protagonist"), ("Ada Pell", "supporting"), ("Liesel Marr", "antagonist"),
    ("Edric Thorne", "supporting"), ("Abel Ferris", "supporting"), ("Tobin Gale", "minor"),
    ("Silas Crane", "supporting"), ("Mother Agathe", "minor"),
]

# Beats for the model-written scene prose. They never state a planted answer.
BEATS = [
    "Wren Halloway returns to the salt-marsh harbour town of Greymouth after her aunt's death and takes over the shuttered chandlery.",
    "Wren meets Ada Pell, a net-mender who knows every boat in the harbour, and they inventory the chandlery's water-damaged stock.",
    "The harbourmaster Edric Thorne visits the chandlery to collect unpaid harbour dues and is gruff but not unkind.",
    "A spring storm rolls in; Wren and Ada help fishermen haul boats up the shingle while Thorne shouts orders.",
    "Wren negotiates with the customs office over her aunt's unpaid duties and meets the officer Silas Crane.",
    "Liesel Marr, who runs the bakery and half the town's gossip, invites Wren to a supper where the talk turns to old wrecks.",
    "Wren finds her aunt's diary pages torn out and starts to suspect her aunt was keeping records for someone.",
    "Ada takes Wren out on the marsh at low tide to show her the old smugglers' paths and the ruined rope-works.",
    "Wren attends a service at the harbour chapel with Mother Agathe and notices the chapel is poorer than it should be.",
    "Market day: Wren sells rope and lamp oil, haggles with Liesel Marr, and hears rumours about the wreck of the Marisol.",
    "Tobin Gale, the young lighthouse keeper's assistant, buys lamp oil on credit and seems nervous.",
    "Wren reads old newspaper cuttings about the night the Marisol was lost with all hands eleven years ago.",
    "Thorne falls ill for a week; Ada nurses him and Wren keeps the harbour log in his place.",
    "Wren and Ada row out to the wreck site of the Marisol at slack water and find only weed and timber.",
    "A quiet chapter: the town prepares for the herring festival and Wren repairs the chandlery's sign.",
    "Silas Crane questions Wren about her aunt's dealings and warns her against digging into old business.",
    "Wren finds a coded list in the chandlery's floorboards: dates, boat names and sums of money.",
    "Liesel Marr hosts the herring festival supper; Wren watches who sits with whom.",
    "Wren and Ada break into the cellar of the Anchor Inn after hearing voices at night.",
    "Mother Agathe tells Wren a story about the old smuggling families of Greymouth.",
    "A second storm; a stranger's body washes up on the shingle and the town gathers.",
    "Wren follows Tobin Gale along the marsh path at dusk and loses him near the rope-works.",
    "Ada falls out with Wren over the risks they are taking and stops coming to the chandlery.",
    "Wren works alone, sorting her aunt's accounts, and notices payments to the chapel.",
    "Silas Crane is seen meeting a ship's captain at night; Wren cannot tell what passes between them.",
    "Wren and Ada reconcile on the harbour wall and agree to finish what they started.",
    "Ada examines the drowned stranger's belongings at the undertaker's while Wren keeps watch.",
    "Wren confronts Tobin Gale, who denies everything and runs.",
    "The rope-works fire is remembered by old men in the Anchor Inn over ale.",
    "Wren visits Thorne, recovered, who tells her more about the night the Marisol was lost.",
    "Edric Thorne dies suddenly; the town mourns and Wren is shaken.",
    "Wren and Ada piece together the coded list and the chapel payments.",
    "Liesel Marr comes to the chandlery with bread and condolences and asks too many questions.",
    "A tense meeting in the customs house: Crane, Wren and the town council.",
    "Wren's past catches up with her: letters from her late mother's friend arrive from the city.",
    "Thorne's funeral at the harbour chapel; the whole town attends.",
    "Wren and Ada lay a trap using the coded list and wait through the night on the marsh.",
    "Captain Abel Ferris, an old sea captain who has watched Wren since she arrived, finally speaks to her alone.",
    "The truth comes out at the Anchor Inn in front of the town; arrests are made.",
    "Spring returns; Wren decides what to do with the last of her aunt's secrets and the chandlery reopens.",
]

# Planted scenarios. chapter numbers are 1-based. Each planted paragraph is
# inserted verbatim into its chapter's prose.
SCENARIOS = [
    {
        "id": "poisoner", "kind": "PA-C6", "query": "Who poisoned the harbourmaster Edric Thorne?",
        "critical": {"chapter": 31, "key": "tipped the blue-glass vial of foxglove into Edric Thorne's tea",
                     "text": "Later, alone with the empty cup, Wren understood what she had seen that morning: it was Liesel Marr who tipped the blue-glass vial of foxglove into Edric Thorne's tea while he signed the harbour book, and Marr who had sent the boy for the doctor too late."},
        "decoys": [
            {"chapter": 4, "key": "Thorne grumbled that the foxglove in the chapel garden",
             "text": "Between orders, Thorne grumbled that the foxglove in the chapel garden was choking the herbs again, and poured himself more tea from the tin pot he carried everywhere, tea so strong it could have poisoned a mule."},
            {"chapter": 18, "key": "the apothecary's foxglove tincture for her heart",
             "text": "Someone at the next table was praising the apothecary's foxglove tincture for her heart, and the harbourmaster, Edric Thorne, laughed that he'd sooner drink poison than the man's tea."},
            {"chapter": 36, "key": "A wreath of foxglove and sea-holly lay on Edric Thorne's coffin",
             "text": "A wreath of foxglove and sea-holly lay on Edric Thorne's coffin, and afterwards there was tea in the chapel hall, where people talked about poison only in the old, joking way they always had."},
        ],
    },
    {
        "id": "second_ledger", "kind": "PA-C6", "query": "Where is the second ledger hidden?",
        "critical": {"chapter": 9, "key": "the second ledger had been sewn into the lining of the altar cloth",
                     "text": "When Mother Agathe lifted the frontal to brush it, Wren saw the stitching and knew: the second ledger had been sewn into the lining of the altar cloth, flat as a hymn sheet, where no customs man would ever lay a hand."},
        "decoys": [
            {"chapter": 2, "key": "The chandlery's own ledger was so swollen with seawater",
             "text": "The chandlery's own ledger was so swollen with seawater that Ada laughed and said a second ledger would have to be started, and they hung the first one to dry beside the altar candles Wren's aunt had kept for the chapel."},
            {"chapter": 14, "key": "the customs ledger lists every hull and every cask",
             "text": "Crane had once boasted that the customs ledger lists every hull and every cask, and that no second ledger could exist in Greymouth without his knowing; Wren thought of that as they rowed home."},
            {"chapter": 24, "key": "sorting receipts into a second ledger of her own",
             "text": "By midnight Wren was sorting receipts into a second ledger of her own, one column for the chandlery, one for the chapel, wondering where her aunt had hidden anything she did not want found."},
        ],
    },
    {
        "id": "tunnel_password", "kind": "PA-C6", "query": "What is the password for the smugglers' tunnel under the Anchor Inn?",
        "critical": {"chapter": 19, "key": "the word at the tunnel door was 'low tide answers'",
                     "text": "Pressed against the cellar wall, they heard the knock and the reply, and Ada mouthed it back to her: the word at the tunnel door was 'low tide answers', given twice, the second time softer."},
        "decoys": [
            {"chapter": 8, "key": "the old smugglers' tunnels had all collapsed",
             "text": "Ada swore the old smugglers' tunnels had all collapsed before her grandmother's time, and that anyone who talked about passwords and secret doors under the Anchor Inn had been reading penny novels."},
            {"chapter": 20, "key": "children in Greymouth still played at smugglers with a password",
             "text": "Mother Agathe smiled that children in Greymouth still played at smugglers with a password and a tunnel made of chairs, and that the Anchor Inn's landlord had been the worst of them as a boy."},
        ],
    },
    {
        "id": "real_father", "kind": "PA-C6", "query": "Who is Wren's real father?",
        "critical": {"chapter": 38, "key": "I am your father, Wren, and your mother made me swear",
                     "text": "Ferris did not look at her when he said it. \"I am your father, Wren, and your mother made me swear never to tell you while I still went to sea.\" He turned his cap in his hands until the brim was ruined."},
        "decoys": [
            {"chapter": 1, "key": "Wren had never known her father",
             "text": "Wren had never known her father; her aunt had only ever said he was a sailor, and that the sea had a long memory and a short temper."},
            {"chapter": 35, "key": "your father would have been proud",
             "text": "The letter from her mother's friend ended kindly: your father would have been proud of you, whoever he was, and so would she."},
        ],
    },
    {
        "id": "lighthouse_dark", "kind": "PA-C6", "query": "Why did the lighthouse go dark on the night the Marisol was wrecked?",
        "critical": {"chapter": 22, "key": "had cut the lamp's oil line on Liesel Marr's orders",
                     "text": "Hidden in the reeds, Wren heard Tobin sobbing it to the dark: eleven years ago his father had cut the lamp's oil line on Liesel Marr's orders, so the Marisol would run onto the bar and her cargo wash up for the taking."},
        "decoys": [
            {"chapter": 11, "key": "the lighthouse lamp burned a gallon of oil a night",
             "text": "Tobin explained that the lighthouse lamp burned a gallon of oil a night in winter, and that on the night of a wreck the keeper's log had to record every hour the light was lit."},
            {"chapter": 12, "key": "the official inquiry found the Marisol lost to the storm",
             "text": "The cutting said the official inquiry found the Marisol lost to the storm alone, and noted only that the lighthouse had been 'reported dim' that night by one fisherman."},
            {"chapter": 30, "key": "Thorne remembered the lighthouse that night as a smudge",
             "text": "Thorne remembered the lighthouse that night as a smudge in the rain, and said he had always blamed the weather, because blaming anything else had seemed too heavy to carry."},
        ],
    },
    {
        "id": "boot_token", "kind": "PA-C6", "query": "What did Ada find in the drowned stranger's boot?",
        "critical": {"chapter": 27, "key": "a brass token stamped with the Ferris crest",
                     "text": "In the toe of the left boot, wrapped in oilcloth, Ada found a brass token stamped with the Ferris crest, the kind the old captains gave to men they trusted to carry messages."},
        "decoys": [
            {"chapter": 21, "key": "his boots were cracked and full of sand",
             "text": "The drowned stranger lay on his back on the shingle; his boots were cracked and full of sand, and someone said he had the look of a ship's messenger."},
            {"chapter": 33, "key": "Liesel asked whether anything had been found on the drowned man",
             "text": "Over the bread, Liesel asked whether anything had been found on the drowned man, his boots or his pockets, and Wren lied and said nothing at all."},
        ],
    },
    {
        "id": "betrayer", "kind": "PA-C6", "query": "Who betrayed the smugglers to the customs office?",
        "critical": {"chapter": 34, "key": "it was Silas Crane's own clerk, Jory Wake, who sold the smugglers' dates",
                     "text": "The council minutes, when Wren finally read them, settled it: it was Silas Crane's own clerk, Jory Wake, who sold the smugglers' dates to the customs office, and Crane who had covered for him."},
        "decoys": [
            {"chapter": 16, "key": "Crane warned that anyone who betrayed the customs office",
             "text": "Crane warned that anyone who betrayed the customs office or helped the smugglers would hang, and that her aunt had come very close to both."},
            {"chapter": 25, "key": "whether the captain was betraying the smugglers or paying them",
             "text": "From the harbour wall Wren could not tell whether the captain was betraying the smugglers or paying them; she only saw Crane nod and the lantern go out."},
        ],
    },
    {
        "id": "customs_deal", "kind": "PA-C6", "query": "What deal did Wren make with the customs officer Silas Crane?",
        "critical": {"chapter": 5, "key": "agreed to forgive her aunt's duties if Wren reported any boat landing after dark",
                     "text": "In the end Crane agreed to forgive her aunt's duties if Wren reported any boat landing after dark at the chandlery steps, and she signed, telling herself she would never have to keep her word."},
        "decoys": [
            {"chapter": 15, "key": "The customs officer bought a new rope",
             "text": "The customs officer bought a new rope for the festival bunting and paid in coin, which Ada said was the first honest deal Crane had made in Greymouth."},
            {"chapter": 34, "key": "The council asked Wren to explain her arrangement with customs",
             "text": "The council asked Wren to explain her arrangement with customs, and she said only that she had paid what her aunt owed, which was nearly true."},
        ],
    },
    {
        "id": "ledger_burial", "kind": "PA-C6", "query": "Where does Wren bury the ledger at the end of the story?",
        "critical": {"chapter": 40, "key": "buried the ledger beneath the third post of the old rope-works pier",
                     "text": "On the first warm morning Wren walked out alone at low tide and buried the ledger beneath the third post of the old rope-works pier, where the next storm would decide what Greymouth was allowed to remember."},
        "decoys": [
            {"chapter": 8, "key": "The old rope-works pier had been half-buried in silt",
             "text": "The old rope-works pier had been half-buried in silt since the fire, and Ada said nothing worth finding had ever been buried there except broken bottles."},
            {"chapter": 32, "key": "They spread the ledger and the coded list side by side",
             "text": "They spread the ledger and the coded list side by side on the counter and matched the dates one by one until the candle burned down."},
        ],
    },
    {
        "id": "locked_room", "kind": "PA-C6", "query": "What is kept in the locked room under the Anchor Inn?",
        "critical": {"chapter": 19, "key": "forty casks of French brandy stamped with the Marisol's mark",
                     "text": "Behind the second door, in the room the landlord kept locked, the lantern showed forty casks of French brandy stamped with the Marisol's mark, salvage that had never been declared."},
        "decoys": [
            {"chapter": 29, "key": "the Anchor Inn's landlord kept the good ale locked",
             "text": "The old men said the Anchor Inn's landlord kept the good ale locked in a back room for weddings and funerals, and that it was better than anything the Marisol ever carried."},
            {"chapter": 6, "key": "Liesel laughed about the locked doors of Greymouth",
             "text": "At supper Liesel laughed about the locked doors of Greymouth, the chapel, the customs house, the Anchor Inn's cellar, and said every town needed its secrets to stay warm."},
        ],
    },
    {
        "id": "rope_fire", "kind": "PA-C6", "query": "Who set the fire at the rope-works?",
        "critical": {"chapter": 39, "key": "Tobin swore it was Liesel Marr who set the rope-works fire",
                     "text": "Before the whole inn, Tobin swore it was Liesel Marr who set the rope-works fire, to burn the records of what the Marisol had really carried, and that his father had held the lamp for her."},
        "decoys": [
            {"chapter": 29, "key": "the rope-works fire had started in the tar shed",
             "text": "The eldest of the old men insisted the rope-works fire had started in the tar shed by accident, and the others argued about it until the landlord rang for closing."},
            {"chapter": 8, "key": "the blackened beams of the rope-works",
             "text": "Ada showed her the blackened beams of the rope-works and said the fire had been the end of honest work in Greymouth, whoever had started it."},
        ],
    },
    {
        "id": "marisol_sinking", "kind": "PA-C6", "query": "How was the Marisol really lost?",
        "critical": {"chapter": 22, "key": "ran onto the Greymouth bar with no light to warn her",
                     "text": "The Marisol, Tobin said, had not been lost to the storm at all: she ran onto the Greymouth bar with no light to warn her, and the men who waited on the shingle took her cargo before the bodies came ashore."},
        "decoys": [
            {"chapter": 12, "key": "the Marisol was lost with all hands",
             "text": "Every cutting agreed that the Marisol was lost with all hands in the great storm, and that the town had raised a fund for the widows."},
            {"chapter": 14, "key": "the wreck of the Marisol lay somewhere under the weed",
             "text": "At slack water Ada said the wreck of the Marisol lay somewhere under the weed, though the currents had moved her timbers a hundred times since."},
        ],
    },
    # PA-H12: a character with many minor appearances and ONE major act.
    {
        "id": "marr_major", "kind": "PA-H12", "query": "What is the most important thing Liesel Marr did in the story?",
        "critical": {"chapter": 31, "key": "tipped the blue-glass vial of foxglove into Edric Thorne's tea"},
        "decoys": [
            {"chapter": 10, "key": "Liesel Marr sold Wren a seed loaf",
             "text": "Liesel Marr sold Wren a seed loaf at twice the price and called it a welcome gift, and Wren paid because everyone was watching."},
            {"chapter": 18, "key": "Liesel Marr gave the toast at the herring festival",
             "text": "Liesel Marr gave the toast at the herring festival, as she did every year, and the town cheered her as if she had caught every fish herself."},
            {"chapter": 33, "key": "Liesel Marr brought a basket of bread",
             "text": "Liesel Marr brought a basket of bread to the chandlery and stayed an hour, admiring the new sign."},
        ],
    },
    {
        "id": "ferris_major", "kind": "PA-H12", "query": "What is the most important thing Captain Abel Ferris revealed?",
        "critical": {"chapter": 38, "key": "I am your father, Wren, and your mother made me swear"},
        "decoys": [
            {"chapter": 3, "key": "Captain Abel Ferris tipped his cap",
             "text": "On the harbour wall Captain Abel Ferris tipped his cap to Wren, as he did to everyone, and went on mending his pipe."},
            {"chapter": 17, "key": "Captain Ferris bought tar and twine",
             "text": "Captain Ferris bought tar and twine and asked after Wren's health in a voice that made Ada raise an eyebrow."},
            {"chapter": 26, "key": "Abel Ferris told the harbour boys a story",
             "text": "Abel Ferris told the harbour boys a story about a whale he had seen off Iceland, and Wren listened from the doorway longer than she meant to."},
        ],
    },
]

"""What the buddy says. Keyed by language, then state (or "random")."""

from __future__ import annotations

import random

from .states import State

LINES: dict[str, dict[str, list[str]]] = {
    "hinglish": {
        State.TYPING_FAST: [
            "Bhai aag laga di keyboard pe 🔥",
            "Itni speed? Keyboard ko bhi chhutti de do!",
            "Flow state ON. Disturb nahi karunga 🤐",
            "Tak-tak-tak-tak... main thak gaya dekh ke 😅",
        ],
        State.TYPING_SLOW: [
            "Soch soch ke likh rahe ho... 🤔",
            "Ek ek word, ekdum dhyaan se.",
            "Writer's block? Chai pi lo ☕",
        ],
        State.SCROLLING: [
            "Scroll, scroll, scroll... kuch mila? 👀",
            "Ungli thak jayegi bhai!",
            "Bas 5 minute aur scroll, phir kaam? 😏",
        ],
        State.WATCHING: [
            "Tutorial time! Notes bhi bana lena 📝",
            "Main bhi dekh raha hoon, popcorn kahan hai? 🍿",
            "2x speed pe dekho, time bachao ⏩",
        ],
        "watching:tutorial": [
            "Padhai chal rahi hai! Notes bana lo, baad me kaam aayenge 📝",
            "Tutorial dekh ke code bhi karna, sirf dekhne se nahi hoga 😉",
            "Pause karke khud try karo, phir aage badho 💪",
        ],
        "watching:udemy": [
            "Udemy course! Certificate pakka 🎓",
            "Lecture chal raha hai, main bhi seekh raha hoon 🤓",
        ],
        "watching:youtube": [
            "YouTube time 🍿 Bas ek video... ya das? 😏",
            "Kya dekh rahe ho? Mujhe bhi dikhao!",
        ],
        "poked": ["Oye! 😣", "Aaah! Sir pe kyun? 🤕", "Kya hua? Bolo na 😅", "Ouch! Halke se yaar 😵"],
        "giggle": ["Hehe gudgudi ho rahi hai 😂", "Hahaha bas karo! 🤣", "Hihihi 😆"],
        "dizzy": ["Bas karo yaar, chakkar aa raha hai 😵‍💫", "Itna click? Main button nahi hoon 😤"],
        "break_offer": [
            "{work} min ho gaye lagatar! {brk} min ka break lo ☕",
            "Bahut kaam ho gaya, {brk} min ka break banta hai 🙆",
        ],
        "break_start": [
            "Main bhi chai pe ja raha hoon ☕ {brk} min baad milte hain!",
            "Break time! Aankhen band, kandhe dheele 😌",
        ],
        "break_nag": ["Oye, break pe ho na? Kaam baad me 😤", "Laptop chhodo, break chal raha hai ☕"],
        "break_skip": ["Lagta hai kuch zaroori kaam hai 💻 Break cancel, {snooze} min baad yaad dilaunga"],
        "lunch_start": ["Lunch time! 🍱 Main bhi khana kha raha hoon", "Khaana khao aaram se 🍛 Kaam baad me"],
        "lunch_walk": ["Khaana ho gaya 😋 Ab thoda dheere dheere tahalte hain 🚶", "Pet bhar gaya! Chalo walk 🚶"],
        "lunch_back": ["Lunch khatam? Wapas kaam pe? 💻"],
        "lunch_end": ["Lunch khatam! Energy full 💪 Chalo kaam pe", "Pet bhi khush, mann bhi khush 😄 Kaam shuru?"],
        "think": [
            "Hmm… dinner me kya banega? 🤔",
            "Soch raha hoon… life me aage kya 🤔",
            "Woh bug kahan se aaya hoga… 🤔",
            "Weekend pe kahan chalein? 🤔",
            "Chai ya coffee? Badi soch 🤔",
        ],
        "breathe_skip": ["Koi baat nahi, kaam karo 💻 Breathing baad me karenge"],
        "break_end": ["Break khatam! Fresh ho gaye? Chalo kaam pe 💪", "Wapas aa gaya! Chalo shuru karte hain 🚀"],
        "breathe_offer": ["Chalo 1 minute saath me saans lete hain 🧘", "Thoda ruk ke deep breathing karein? 🌬️"],
        "breathe_in": ["Saans andar lo… {n}"],
        "breathe_hold": ["Roko… {n}"],
        "breathe_out": ["Dheere dheere bahar… {n}"],
        "breathe_end": ["Shabash! Kaisa laga? 😌", "Badhiya! Mind fresh ho gaya na? ✨"],
        "music": ["Gaana bajao, mood banao 🎵", "Ye wala achha hai! 🎶", "Main bhi naach raha hoon andar se 🕺"],
        State.AFK: ["Kahan gaye? Main yahin hoon... 🥱", "Hello? Koi hai?"],
        State.SLEEPING: ["Zzz... jab aao to jaga dena 😴"],
        State.WAKING: ["Aa gaye! Miss kiya 😄", "Oh! Main so gaya tha kya? 😳", "Welcome back boss!"],
        State.HAPPY: ["Hehe 😄", "Haan bolo?", "Main yahin hoon!", "Kya scene hai?"],
        State.STRETCH: [
            "Bahut der se baithe ho. Utho, stretch karo! 🙆",
            "Paani piyo, aankhon ko aaram do 💧",
        ],
        "random": [
            "Fun fact: main kabhi bore nahi hota. Kyunki tum ho 😎",
            "Bug nahi, feature hai. Yaad rakhna.",
            "Kya chal raha hai? Main bas yahin chill kar raha hoon.",
            "Ek break le lo, duniya nahi bhaagegi.",
            "Code compile ho gaya? Party! 🎉",
        ],
    },
    "en": {
        State.TYPING_FAST: ["You're on fire! 🔥", "Keyboard's begging for mercy 😅", "Flow state. I'll stay quiet 🤐"],
        State.TYPING_SLOW: ["Thinking it through... 🤔", "Every word counts."],
        State.SCROLLING: ["Scroll, scroll, scroll... found it yet? 👀", "Just five more minutes? 😏"],
        State.WATCHING: ["Tutorial time! Take notes 📝", "Got popcorn? 🍿"],
        "watching:tutorial": ["Learning time! Take notes 📝", "Pause and try it yourself 💪"],
        "watching:udemy": ["Udemy course! Certificate incoming 🎓"],
        "watching:youtube": ["YouTube time 🍿 Just one video... right? 😏"],
        "poked": ["Ouch! 😣", "Hey! Not the head 🤕", "What's up? 😅"],
        "giggle": ["Hehe, that tickles 😂", "Hahaha stop! 🤣"],
        "dizzy": ["Stop, I'm getting dizzy 😵‍💫", "I'm not a button 😤"],
        "break_offer": ["{work} minutes straight! Take a {brk}-minute break ☕"],
        "break_start": ["I'm grabbing tea too ☕ See you in {brk} min!"],
        "break_nag": ["Hey, you're on a break! 😤"],
        "break_skip": ["Looks like something important 💻 Break cancelled, I'll remind you in {snooze} min"],
        "lunch_start": ["Lunch time! 🍱 I'm eating too"],
        "lunch_walk": ["Done eating 😋 Let's take a slow walk 🚶"],
        "lunch_back": ["Lunch over? Back to work? 💻"],
        "lunch_end": ["Lunch is over! Fully charged 💪"],
        "think": ["Hmm… what's for dinner? 🤔", "Where did that bug come from… 🤔", "Tea or coffee? Big decision 🤔"],
        "breathe_skip": ["No problem, get back to work 💻 We'll breathe later"],
        "break_end": ["Break's over! Feeling fresh? Let's go 💪"],
        "breathe_offer": ["Let's breathe together for a minute 🧘"],
        "breathe_in": ["Breathe in… {n}"],
        "breathe_hold": ["Hold… {n}"],
        "breathe_out": ["Slowly out… {n}"],
        "breathe_end": ["Nice! Feel better? 😌"],
        "music": ["Nice tune 🎵", "I'm dancing on the inside 🕺"],
        State.AFK: ["Where'd you go? 🥱", "Hello? Anyone there?"],
        State.SLEEPING: ["Zzz... wake me when you're back 😴"],
        State.WAKING: ["You're back! 😄", "Oh! Was I asleep? 😳"],
        State.HAPPY: ["Hehe 😄", "Yes?", "I'm here!"],
        State.STRETCH: ["You've been sitting a while. Stretch! 🙆", "Drink some water 💧"],
        "random": ["It's not a bug, it's a feature.", "Take a break, the world can wait.", "Just chilling here 😎"],
    },
}

LANGUAGES = {"hinglish": "Hinglish", "en": "English"}


def line_for(key: State | str, language: str = "hinglish", rng: random.Random | None = None) -> str | None:
    table = LINES.get(language) or LINES["en"]
    options = table.get(key) or LINES["en"].get(key)
    if not options and isinstance(key, str) and ":" in key:
        return line_for(State(key.split(":", 1)[0]), language, rng)
    if not options:
        return None
    return (rng or random).choice(options)

# Demo video script (target 2:45, max 3:00)

Record your screen with your microphone. Use **live mode** if your keys work; the same script also works in demo mode
(type the caller lines). Say aloud which mode you are in.

| Time | On screen | Say |
|---|---|---|
| 0:00-0:20 | Overview page | "This is a voice assistant for a clinic. It uses Pipecat, ElevenLabs and Gemini. The badge shows I am in [live / demo] mode." |
| 0:20-0:40 | Doctors page, filter Cardiology | "These are real slots from the database. Searching and filtering work, and slots are live." |
| 0:40-1:40 | Press **Try call**, then speak | "I'd like to see a cardiologist tomorrow morning." → pick a slot → give your number → listen to the read-back → say "yes". Show the transcript and the booking confirmation card. |
| 1:40-1:55 | Close modal, Appointments page | "The new row is highlighted, and the phone number is masked." |
| 1:55-2:25 | New call: cancel | "I want to cancel my appointment." → number → "yes" → confirm. Show the cancelled card and status. |
| 2:25-2:45 | Try a wrong number or an emergency | Say a different number: the agent finds nothing and cancels nothing. Or say "chest pain": it sends you to emergency services. |
| 2:45-3:00 | Live activity page | "Every tool call and result appears here in real time. Thanks for watching." |

Tips: use a number such as 98765 43210. Check the microphone level first. Do not show your `.env` file or API keys on screen.

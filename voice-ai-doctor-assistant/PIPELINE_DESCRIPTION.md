# Pipeline Description (draft - rewrite in your own words before submitting)

The assistant is a real-time voice pipeline built with Pipecat. The browser captures the microphone and sends audio over
WebRTC (SmallWebRTC) to a FastAPI backend. Silero VAD finds where the caller starts and stops speaking. ElevenLabs
speech-to-text turns the speech into text. The text goes to a Gemini model that has three tools:
`check_doctor_availability`, `book_appointment` and `cancel_appointment`. When Gemini calls a tool, the backend runs it against a
SQLite database and returns the result. Gemini then writes the reply, ElevenLabs text-to-speech turns it into audio, and the audio
goes back to the browser over the same WebRTC connection.

The caller is identified only by the phone number they say. Before a booking or cancellation the agent reads the number back and waits
for a clear yes; the tools refuse to act without that confirmation. The agent says "booked" or "cancelled" only after the database
operation succeeded, never gives medical advice, and sends emergencies to emergency services.

A React dashboard shows doctors, slots and appointments. The backend pushes every change to it through Server-Sent Events, so rows
update while the call is still going.

Without API keys the app runs in a clearly labelled demo mode: a scripted agent replaces the LLM and speech services, but bookings and
cancellations are still real database operations.

Honest note: the live Pipecat path was written from the Pipecat 1.x docs and could not be run during development (no network in the build
environment). See IMPLEMENTATION_REPORT.md.

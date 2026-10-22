"""Plain-language descriptions of observed state, never model thoughts."""


def describe_activity(*, active, connected, starting, ending, reasoning,
                      interrupted, question_ready, pending, speaking, voice_busy):
    if ending:
        return "ending", "Closing the conversation", "Finishing the session and releasing the video connection."
    if starting:
        return "connecting", "Opening your conversation", "Connecting the conversation agent to the video room."
    if reasoning:
        return "reasoning", "Working with your question", "Using the selected profile and assessment guidance to prepare a response."
    if interrupted:
        return "pausing", "Making room for you", "Waiting for speech to stop while preserving our place in the debrief."
    if not active:
        return "ready", "Ready when you are", "Choose a family profile, then begin your conversation."
    if not connected:
        return "disconnected", "Video connection unavailable", "The session exists, but the agent is not connected. End the session before trying again."
    if voice_busy:
        return "listening", "Receiving your voice question", "Processing incoming speech before the conversation continues."
    if speaking:
        return "speaking", "Sharing the next thought", "Speech has started. The app is tracking our place so you can interrupt."
    if pending:
        return "preparing", "Preparing the next voice response", "Text has been submitted for speech. Waiting for the playback start signal."
    if question_ready:
        return "question", "Your turn", "The debrief is paused. Ask a question, or continue where we left off."
    return "between", "A moment to reflect", "The current speech has finished. Continue to the next section when you are ready."

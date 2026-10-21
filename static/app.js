let callFrame = null;
let conversationId = null;


const statusElement =
    document.getElementById("status");

const outputElement =
    document.getElementById("output");


function setStatus(message) {
    statusElement.textContent =
        `Status: ${message}`;
}


function showOutput(data) {
    outputElement.textContent =
        JSON.stringify(
            data,
            null,
            2
        );
}


async function loadPersonas() {
    try {
    const response =
        await fetch("/api/personas");

    const data =
        await response.json();

    if (!response.ok) {
        throw new Error(
            data.error ||
            "Unable to load personas."
        )
    }

    const select =
        document.getElementById(
            "person-select"
        );

    select.innerHTML = "";

    for (
        const person
        of data.personas
    ) {
        const option =
            document.createElement(
                "option"
            );

        option.value =
            person.file;

        option.textContent =
            person.family_role
                ? `${person.display_name} — ${person.family_role}`
                : person.display_name;

        select.appendChild(
            option
        );
    }
    } catch (error) {
    console.error(
        "Persona loading error:",
        error
    )
    }
}


async function postJson(
    url,
    body = null
) {
    const options = {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        }
    };

    if (body !== null) {
        options.body =
            JSON.stringify(body);
    }

    const response =
        await fetch(
            url,
            options
        );

    const data =
        await response.json();

    showOutput(data);

    if (!response.ok) {
        throw new Error(
            data.error ||
            `Request failed: ${response.status}`
        );
    }

    return data;
}


async function startSession() {
    try {
        const personSelect =
            document.getElementById(
                "person-select"
            );
        
        const selectedFile =
            personSelect.value;
        
        if (!selectedFile) {
            setStatus(
                "Select a person first."
            );
            return;
        }

        setStatus(
            "Loading selected profile..."
        );

        await postJson(
            "/api/person/select",
            {
                file: selectedFile
            }
        );
    
        personSelect.disabled = true;

// Everything else below is tried-and-true: \\

        setStatus(
            "Creating Tavus conversation..."
        );

        const data =
            await postJson(
                "/api/session/start"
            );

        conversationId =
            data.conversation.conversation_id;

        if (callFrame) {
            await callFrame.destroy();
            callFrame = null;
        }

        setStatus(
            "Joining Tavus..."
        );

        callFrame =
            window.DailyIframe.createFrame(
                document.getElementById(
                    "video-container"
                ),
                {
                    showLeaveButton: false,
                    iframeStyle: {
                        width: "720px",
                        height: "480px",
                        border: "0"
                    }
                }
            );

        const joinOptions = {
            url:
                data.conversation
                    .conversation_url,

            userName: data.voice_user_name,
            startVideoOff: true,
            startAudioOff: true
        };

        if (
            data.conversation.meeting_token
        ) {
            joinOptions.token =
                data.conversation
                    .meeting_token;
        }

        callFrame.on(
            "joined-meeting",
            () => {
                console.log(
                    "Browser joined Daily meeting."
                );

                setStatus(
                    "Connected"
                );
            }
        );

        callFrame.on(
            "error",
            (event) => {
                console.error(
                    "Daily error:",
                    event
                );

                setStatus(
                    "Daily error"
                );
            }
        );

        callFrame.on(
            "left-meeting",
            () => {
                setStatus(
                    "Disconnected"
                );
            }
        );

        await callFrame.join(
            joinOptions
        );

        /*
         * IMPORTANT:
         * Browser is now actually joined.
         * NOW tell XQ/Tavus to speak.
         */

        setStatus(
            "Connected — starting debrief..."
        );

        await postJson(
            "/api/debrief/tracked/next"
        );

        setStatus("Debrief active — unmute in the call to ask by voice.");

    } catch (error) {
        console.error(error);

        setStatus(
            `Error: ${error.message}`
        );
    }
}


async function speakCurrent() {
    try {
        await postJson(
            "/api/debrief/speak"
        );
    } catch (error) {
        console.error(error);
    }
}


async function nextSection() {
    try {
        await postJson(
            "/api/debrief/next"
        );
    } catch (error) {
        console.error(error);
    }
}


async function repeatSection() {
    try {
        await postJson(
            "/api/debrief/repeat"
        );
    } catch (error) {
        console.error(error);
    }
}


async function restartDebrief() {
    try {
        await postJson(
            "/api/debrief/restart"
        );
    } catch (error) {
        console.error(error);
    }
}


async function askQuestion() {
    const input =
        document.getElementById(
            "question-input"
        );

    const question =
        input.value.trim();

    if (!question) {
        return;
    }

    try {
        setStatus(
            "Preparing question..."
        );

        let statusResponse =
            await fetch("/api/status");

        let status =
            await statusResponse.json();

        let playback =
            status.playback || {};

        /*
         * If tracked narration is currently
         * speaking, interrupt it first.
         */
        if (
            playback.phase === "narrating"
            &&
            playback.tracked_pending
        ) {
            setStatus(
                "Interrupting narration..."
            );

            await postJson(
                "/api/debrief/interrupt"
            );

            const timeoutMs = 10000;
            const pollMs = 100;
            const started = Date.now();

            while (true) {
                await new Promise(
                    resolve =>
                        setTimeout(
                            resolve,
                            pollMs
                        )
                );

                statusResponse =
                    await fetch(
                        "/api/status"
                    );

                status =
                    await statusResponse.json();

                playback =
                    status.playback || {};

                if (
                    playback.phase
                    === "question_ready"
                    &&
                    !playback.interruption_pending
                ) {
                    break;
                }

                if (
                    Date.now() - started
                    > timeoutMs
                ) {
                    throw new Error(
                        "Timed out waiting "
                        + "for narration to stop."
                    );
                }
            }
        }

        setStatus(
            "XQ is reasoning..."
        );

        await postJson(
            "/api/question",
            {
                question: question
            }
        );

        input.value = "";
        stopQuestionKeepalive();

        setStatus(
            "Answering — narration will "
            + "resume automatically."
        );

    } catch (error) {
        console.error(error);

        setStatus(
            `Error: ${error.message}`
        );
    }
}


async function endSession() {
    try {
        setStatus(
            "Ending session..."
        );

        /*
         * Leave browser room first.
         */

        if (callFrame) {
            try {
                await callFrame.leave();
            } catch (error) {
                console.warn(
                    "Browser leave warning:",
                    error
                );
            }

            callFrame.destroy();
            callFrame = null;
        }

        /*
         * Then tell backend/Tavus
         * to end the conversation.
         */

        await postJson(
            "/api/session/end"
        );

        conversationId = null;
        stopQuestionKeepalive();

        setStatus(
            "Session ended"
        );

        document
            .getElementById(
                "person-select"
            )
            .disabled = false;

    } catch (error) {
        console.error(error);

        setStatus(
            `Error: ${error.message}`
        );
    }
}


/*
 * BUTTON WIRING
 */

document
    .getElementById(
        "start-button"
    )
    .addEventListener(
        "click",
        startSession
    );


document
    .getElementById(
        "speak-button"
    )
    .addEventListener(
        "click",
        speakCurrent
    );


document
    .getElementById(
        "next-button"
    )
    .addEventListener(
        "click",
        nextSection
    );


document
    .getElementById(
        "repeat-button"
    )
    .addEventListener(
        "click",
        repeatSection
    );


document
    .getElementById(
        "restart-button"
    )
    .addEventListener(
        "click",
        restartDebrief
    );


document
    .getElementById(
        "ask-button"
    )
    .addEventListener(
        "click",
        askQuestion
    );


document
    .getElementById(
        "end-button"
    )
    .addEventListener(
        "click",
        endSession
    );


    loadPersonas();

// Keep question mode open while someone actively edits a typed question.
let questionKeepalive = null;
let lastQuestionInput = 0;

function stopQuestionKeepalive() {
    clearInterval(questionKeepalive);
    questionKeepalive = null;
}

async function keepQuestionOpen() {
    if (Date.now() - lastQuestionInput > 15000) {
        stopQuestionKeepalive();
        return;
    }
    try {
        await fetch("/api/question/keepalive", {method: "POST"});
    } catch (error) {
        console.warn("Question keepalive failed:", error);
    }
}

const questionInput = document.getElementById("question-input");
questionInput.addEventListener("input", () => {
    lastQuestionInput = Date.now();
    if (questionKeepalive === null) {
        keepQuestionOpen();
        questionKeepalive = setInterval(keepQuestionOpen, 5000);
    }
});
questionInput.addEventListener("blur", stopQuestionKeepalive);

document.getElementById("dismiss-button").addEventListener("click", async () => {
    try {
        await postJson("/api/question/dismiss");
        stopQuestionKeepalive();
        setStatus("Question dismissed — narration resumed.");
    } catch (error) {
        setStatus(`Error: ${error.message}`);
    }
});

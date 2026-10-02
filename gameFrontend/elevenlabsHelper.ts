




export default async function speakMoveReasoning(textToSpeak: any) {

    if (!textToSpeak) {
        return;
    }

const response = await fetch("http://localhost:8787/speak", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: textToSpeak }),
    });

    const blob = await response.blob();
    const url = URL.createObjectURL(blob);

    const audio = new Audio(url);
    await audio.play();

    audio.onended = () => URL.revokeObjectURL(url);
    return
  }


# Add Local STT Option to ASL Robot

## Goal
Add local Speech-to-Text using OpenAI Whisper as an alternative to the existing Google Cloud STT, allowing easy comparison of accuracy and latency. The existing cloud STT must continue working unchanged.

---

## Requirements

1. **Keep cloud STT working** - No changes to existing Google Cloud STT functionality
2. **Add local STT option** - Use OpenAI Whisper for offline speech recognition
3. **Easy switching** - Use `.env` variable `STT_ENGINE=cloud` or `STT_ENGINE=local` to switch
4. **Same interface** - Both engines output identical format to downstream pipeline
5. **No pipeline changes** - AI, DB, and Motion threads remain completely unchanged

---

## Architecture

Use **Factory Pattern** to create appropriate STT engine based on configuration:

```
STT Factory → Creates → Cloud STT OR Local STT (based on .env)
                              ↓
                        Same interface
                              ↓
                      Wake word detection
                              ↓
                        FileIO.stt_queue
                              ↓
                    (AI → DB → Motion unchanged)
```

---

## Implementation Tasks

### 1. Create Abstract Base Class

**File**: `src/speech_to_text/base_stt.py` (NEW)

Define interface that both cloud and local STT must implement:
- `start_stream()` - Initialize audio stream
- `stop_stream()` - Clean up resources
- `get_transcripts()` - Generator yielding transcript strings
- `is_ready()` - Check if engine is ready
- `engine_name` - Property returning engine name for logging

---

### 2. Refactor Existing Cloud STT

**File**: `src/speech_to_text/cloud_stt.py` (NEW)

Move existing `stt.py` code into a class that inherits from `BaseSTT`. No functionality changes, just wrap it in the new interface.

---

### 3. Implement Local STT with Whisper

**File**: `src/speech_to_text/local_stt.py` (NEW)

Create Whisper-based STT that:
- Loads Whisper model (size from config, default: 'base')
- Uses PyAudio for microphone input
- Processes audio in chunks (3-second chunks recommended)
- Runs Whisper transcription in background thread
- Yields transcripts through same interface as cloud STT

**Key implementation details**:
- Buffer audio until chunk size reached (3 seconds worth)
- Process chunks through Whisper in separate thread
- Put results in queue that `get_transcripts()` yields from
- Normalize audio to float32 in [-1, 1] range for Whisper

---

### 4. Create Factory

**File**: `src/speech_to_text/stt_factory.py` (NEW)

Factory that:
- Reads `STT_ENGINE` from environment (defaults to 'cloud')
- Creates `CloudSTT` if `STT_ENGINE=cloud`
- Creates `LocalSTT` if `STT_ENGINE=local`
- Loads appropriate config for each engine type
- Raises error if invalid engine type

---

### 5. Update STT Thread

**File**: `src/io/stt_io.py` (MODIFY)

Replace direct STT instantiation with factory:
- Use `STTFactory.create_stt()` instead of direct imports
- Rest of wake word detection logic stays identical
- No other changes needed

---

### 6. Add Configuration

**File**: `.env` (UPDATE)

Add:
```bash
# STT Engine: 'cloud' or 'local'
STT_ENGINE=cloud

# Local STT config (only used if STT_ENGINE=local)
LOCAL_STT_MODEL=base
LOCAL_STT_DEVICE=cpu
```

**File**: `requirements.txt` (UPDATE)

Add:
```
openai-whisper
torch
torchaudio
numpy
```

---

### 7. Add Simple Test Script

**File**: `src/testing/test_stt.py` (NEW)

Create quick test that:
- Takes engine type as argument (`cloud` or `local`)
- Creates that engine
- Starts stream
- Prints first 10 transcripts
- Stops stream

Usage: `python -m src.testing.test_stt local`

---

## Technical Specifications

### Whisper Configuration
- **Model size**: 'base' (150MB, good balance)
- **Chunk duration**: 3.0 seconds
- **Sample rate**: 16000 Hz
- **Device**: 'cpu' (use 'cuda' if GPU available)
- **Language**: 'en'

### Audio Processing
- **Format**: 16-bit PCM
- **Channels**: 1 (mono)
- **Buffer**: Accumulate until 3 seconds of audio, then process
- **Normalization**: Convert int16 to float32, divide by 32768

### Thread Safety
- Local STT runs Whisper in background thread
- Use `queue.Queue` for thread-safe transcript passing
- Main thread yields from queue in `get_transcripts()`

---

## Testing

After implementation:

1. **Test cloud still works**: 
   ```bash
   STT_ENGINE=cloud python -m src.testing.test_stt cloud
   ```

2. **Test local works**:
   ```bash
   STT_ENGINE=local python -m src.testing.test_stt local
   ```

3. **Test with full pipeline**:
   - Set `STT_ENGINE=local` in `.env`
   - Run `python -B -m src.main`
   - Say wake word and test transcription

---

## Success Criteria

- ✅ Cloud STT still works exactly as before
- ✅ Local STT transcribes speech accurately
- ✅ Wake words detected with both engines
- ✅ Easy switching via `.env` file
- ✅ No changes needed to AI/DB/Motion threads
- ✅ Can run full pipeline with either engine

---

## Notes

- First run downloads Whisper model (~150MB for 'base')
- Local STT works completely offline after initial download
- Both engines should have similar wake word detection performance
- Local STT may have lower latency than cloud (no network round-trip)
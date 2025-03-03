// scripts.js 完整代码
let mediaStream = null;
let mediaRecorder;
let recordedChunks = [];
let isRecording = false;
let selectedFileName = null;
let realtimeAnalyzer = null;
let standardKeypoints = null;
let isRealtimeAnalyzing = false;
let processingInterval = null;
const TARGET_FPS = 17; // 修改为 17 FPS 以减少延迟

// 元素引用
const videoPreview = document.getElementById('videoPreview');
const uploadList = document.getElementById('uploadList');

// 按钮事件绑定
document.getElementById('openCamera').addEventListener('click', openCamera);
document.getElementById('closeCamera').addEventListener('click', closeCamera);
document.getElementById('startRecord').addEventListener('click', startRecording);
document.getElementById('stopRecord').addEventListener('click', stopRecording);
document.getElementById('uploadVideo').addEventListener('click', uploadVideo);
document.getElementById('analyzeVideo').addEventListener('click', analyzeVideo);
document.getElementById('realtimeAnalyze').addEventListener('click', realtimeAnalyze);
document.getElementById('refreshList').addEventListener('click', () => loadFileList());

// 初始化加载文件列表
loadFileList();

async function openCamera() {
  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({
      video: {
        width: { ideal: 640 },
        height: { ideal: 480 },
      },
    });
    videoPreview.srcObject = mediaStream;
    videoPreview.play();
  } catch (error) {
    console.error('摄像头访问失败:', error);
    alert('无法访问摄像头，请检查权限和连接');
  }
}

function closeCamera() {
  if (mediaStream) {
    mediaStream.getTracks().forEach((track) => track.stop());
    mediaStream = null;
    videoPreview.srcObject = null;
    videoPreview.src = '';
  }
  if (processingInterval) clearInterval(processingInterval);
  isRealtimeAnalyzing = false;
}

async function startRecording() {
  if (!mediaStream) {
    alert('请先打开摄像头！');
    return;
  }

  try {
    const mimeType = 'video/mp4; codecs=avc1';
    if (!MediaRecorder.isTypeSupported(mimeType)) {
      throw new Error('当前浏览器不支持MP4录制，请使用Chrome或Edge浏览器');
    }

    mediaRecorder = new MediaRecorder(mediaStream, { mimeType });

    mediaRecorder.ondataavailable = (event) => {
      if (event.data.size > 0) {
        recordedChunks.push(event.data);
      }
    };

    mediaRecorder.onstop = async () => {
      const blob = new Blob(recordedChunks, { type: mimeType });
      await sendVideoToServer(blob);
      recordedChunks = [];
    };

    mediaRecorder.start(200);
    isRecording = true;
    updateButtonStates();
  } catch (error) {
    alert(error.message);
  }
}

function stopRecording() {
  if (mediaRecorder && isRecording) {
    mediaRecorder.stop();
    isRecording = false;
    updateButtonStates();
  }
}

async function sendVideoToServer(blob) {
  try {
    const filename = `${Date.now()}.mp4`;
    const file = new File([blob], filename, { type: 'video/mp4' });

    const formData = new FormData();
    formData.append('video', file);

    const response = await fetch('/upload', {
      method: 'POST',
      body: formData,
    });

    if (response.ok) {
      alert('视频已成功保存！');
      loadFileList();
    } else {
      throw new Error(`上传失败：${response.statusText}`);
    }
  } catch (error) {
    alert(error.message);
  }
}

function uploadVideo() {
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = 'video/mp4, video/webm, video/avi';

  input.onchange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('video', file);

    try {
      const response = await fetch('/upload', {
        method: 'POST',
        body: formData,
      });

      if (response.ok) {
        alert('上传成功！');
        loadFileList();
      } else {
        const error = await response.json();
        throw new Error(error.error || '上传失败');
      }
    } catch (error) {
      alert(error.message);
    }
  };

  input.click();
}

function updateButtonStates() {
  document.getElementById('startRecord').disabled = isRecording;
  document.getElementById('stopRecord').disabled = !isRecording;
  document.getElementById('openCamera').disabled = isRecording;
}

function loadFileList() {
  fetch('/uploads')
    .then((response) => response.json())
    .then((files) => {
      uploadList.innerHTML = files
        .map(
          (file) =>
            `<div class="file-item" onclick="selectFile('${file.name.replace(/'/g, "\\'")}')">
                    ${file.name}
                    <button onclick="downloadFile('${file.name.replace(
                      /'/g,
                      "\\'",
                    )}')">下载</button>
                </div>`,
        )
        .join('');
    });
}

function downloadFile(filename) {
  window.open(`/download/${filename}`, '_blank');
}

function selectFile(filename) {
  selectedFileName = filename;
  document.querySelectorAll('.file-item').forEach((item) => {
    item.classList.remove('selected');
  });
  event.currentTarget.classList.add('selected');
}

async function analyzeVideo() {
  if (!selectedFileName) {
    alert('请先选择要分析的视频');
    return;
  }

  const processingAlert = document.getElementById('processingAlert');
  try {
    processingAlert.textContent = '正在分析视频...';
    processingAlert.style.display = 'block';
    document.getElementById('analyzeVideo').disabled = true;

    const response = await fetch('/analyze', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        filename: selectedFileName,
      }),
    });

    const result = await response.json();
    if (response.ok) {
      alert('分析完成！结果视频已生成');
      loadFileList();
    } else {
      throw new Error(result.error || '分析失败');
    }
  } catch (error) {
    alert(error.message);
  } finally {
    processingAlert.style.display = 'none';
    document.getElementById('analyzeVideo').disabled = false;
  }
}

// 修改后的实时分析函数
async function realtimeAnalyze() {
  const analyzeBtn = document.getElementById('realtimeAnalyze');
  const videoPreview = document.getElementById('videoPreview');
  const processedFeed = document.getElementById('processedFeed');
  const loadingIndicator = document.getElementById('loadingIndicator');

  if (isRealtimeAnalyzing) {
    clearInterval(processingInterval);
    loadingIndicator.style.display = 'none';
    processedFeed.style.display = 'none';
    closeCamera();
    analyzeBtn.textContent = '实时分析';
    isRealtimeAnalyzing = false;
    return;
  }

  // 启动摄像头
  mediaStream = await navigator.mediaDevices.getUserMedia({
    video: { width: 640, height: 480 },
  });
  videoPreview.srcObject = mediaStream;
  await videoPreview.play();

  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d');
  canvas.width = videoPreview.videoWidth;
  canvas.height = videoPreview.videoHeight;

  // 显示弹出式加载提示
  loadingIndicator.style.display = 'block';
  processedFeed.style.display = 'none';

  // 设置处理帧率（15 FPS）
  const intervalTime = 1000 / TARGET_FPS;

  processingInterval = setInterval(async () => {
    try {
      ctx.drawImage(videoPreview, 0, 0);
      const imageData = canvas.toDataURL('image/jpeg', 0.5); // 降低质量到 0.5 以减少数据量
      const response = await fetch('/process_frame', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ image: imageData }),
      });

      if (response.ok) {
        const result = await response.json();
        processedFeed.src = `data:image/jpeg;base64,${result.processed}`;
        // 隐藏加载提示，显示处理后的画面
        loadingIndicator.style.display = 'none';
        processedFeed.style.display = 'block';
      }
    } catch (error) {
      console.error('Frame processing error:', error);
    }
  }, intervalTime);

  analyzeBtn.textContent = '停止分析';
  isRealtimeAnalyzing = true;
}

import cv2
import json
import numpy as np
from ultralytics import YOLO
import os
from fastdtw import fastdtw
from tqdm import tqdm


def process_pose_videos(
    video1_path: str,
    video2_path: str,
    output_vid1_path: str,
    output_vid2_path: str,
    keypoints1_path: str,
    keypoints2_path: str,
):
    """
    处理双视频的骨骼关键点提取与对齐

    :param video1_path: 第一个输入视频路径
    :param video2_path: 第二个输入视频路径
    :param output_vid1_path: 第一个处理视频输出路径
    :param output_vid2_path: 第二个处理视频输出路径
    :param keypoints1_path: 第一个视频关键点保存路径
    :param keypoints2_path: 第二个视频关键点保存路径
    """
    # 初始化YOLO模型
    model = YOLO(r"models\yolo11n-pose.pt")

    def get_video_info(vid_path):
        """获取视频基本信息"""
        cap = cv2.VideoCapture(vid_path)
        if not cap.isOpened():
            raise ValueError(f"无法打开视频 {vid_path}")

        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        # 准确计算总帧数
        total = 0
        while cap.isOpened():
            ret, _ = cap.read()
            if not ret:
                break
            total += 1
        cap.release()
        return total, fps, (width, height)

    # 获取视频参数
    frames1, fps1, (w1, h1) = get_video_info(video1_path)
    frames2, fps2, (w2, h2) = get_video_info(video2_path)
    target_frames = max(frames1, frames2)

    # 处理单个视频的闭包函数
    def process_video(input_path, output_path, kps_path, fps, size):
        """处理单个视频的通用流程"""
        # 检查输出文件是否已存在
        if os.path.exists(output_path) and os.path.exists(kps_path):
            print(f"输出文件已存在，跳过处理: {output_path} 和 {kps_path}")
            return
        # 创建输出目录
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        os.makedirs(os.path.dirname(kps_path), exist_ok=True)

        # 初始化视频读写器
        cap = cv2.VideoCapture(input_path)
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(output_path, fourcc, fps, size)

        keypoints = []
        frame_count = 0

        # 使用tqdm显示进度条
        with tqdm(
            total=target_frames, desc=f"Processing {os.path.basename(input_path)}"
        ) as pbar:
            while frame_count < target_frames:
                ret, frame = cap.read()
                if not ret:  # 视频循环
                    cap.release()
                    cap = cv2.VideoCapture(input_path)
                    continue

                # 姿态估计
                results = model(frame, verbose=False)
                out.write(results[0].plot())  # 写入标注视频

                # 关键点处理
                if results[0].keypoints.xy.shape[1] > 0:
                    kps = results[0].keypoints.xy[0].cpu().numpy()
                    # 基于肩膀中点归一化
                    mid = (kps[5] + kps[6]) / 2
                    norm_kps = (kps - mid).tolist()
                else:
                    norm_kps = [[np.nan, np.nan]] * 17

                keypoints.append(norm_kps)
                frame_count += 1
                pbar.update(1)

                if frame_count >= target_frames:
                    break

        cap.release()
        out.release()

        # 关键点补全（循环填充）
        if len(keypoints) < target_frames:
            keypoints = (keypoints * (target_frames // len(keypoints) + 1))[
                :target_frames
            ]

        # 保存关键点
        with open(kps_path, "w") as f:
            json.dump(
                keypoints,
                f,
                default=lambda x: x.tolist() if isinstance(x, np.ndarray) else x,
            )

    # 处理两个视频
    process_video(video1_path, output_vid1_path, keypoints1_path, fps1, (w1, h1))
    process_video(video2_path, output_vid2_path, keypoints2_path, fps2, (w2, h2))


def align_keypoints(json_path1, json_path2, output_path1, output_path2):
    """
    对齐两个关键点序列并保存结果

    参数：
    json_path1: 第一个视频的JSON文件路径
    json_path2: 第二个视频的JSON文件路径
    output_path1: 对齐后的第一个序列输出路径
    output_path2: 对齐后的第二个序列输出路径
    """

    # 加载JSON数据
    with open(json_path1, "r") as f:
        keypoints1 = json.load(f)
    with open(json_path2, "r") as f:
        keypoints2 = json.load(f)

    # 填充关键点到每帧17个（确保每帧17个关键点）
    def pad_frames(frames):
        return [frame + [[0.0, 0.0]] * (17 - len(frame)) if len(frame) <17 else frame[:17] for frame in frames]

    padded1 = pad_frames(keypoints1)
    padded2 = pad_frames(keypoints2)

    # 展平为34维向量序列，替换NaN为0
    def flatten(frames):
        flattened = []
        for frame in frames:
            # 替换NaN坐标并限制为17个关键点
            processed = []
            for kp in frame[:17]:  # 确保只取前17个关键点
                if isinstance(kp, list) and len(kp) == 2:
                    processed.append([
                        kp[0] if not np.isnan(kp[0]) else 0.0,
                        kp[1] if not np.isnan(kp[1]) else 0.0
                    ])
                else:
                    processed.append([0.0, 0.0])  # 无效关键点处理
            # 展平为34维向量
            flattened.append(np.array([coord for kp in processed for coord in kp]))
        return flattened

    flat1 = flatten(padded1)
    flat2 = flatten(padded2)

    # 执行DTW对齐
    _, path = fastdtw(flat1, flat2, dist=2)

    # 重建对齐后的序列
    aligned1 = [padded1[i] for i, _ in path]
    aligned2 = [padded2[j] for _, j in path]

    # 保存结果时确保数据格式正确
    def format_output(sequence):
        """确保每帧包含17个关键点，每个关键点有2个坐标"""
        formatted = []
        for frame in sequence:
            # 截断或填充到17个关键点
            adjusted = frame[:17] + [[0.0, 0.0]] * (17 - len(frame[:17]))
            formatted.append([[float(coord) for coord in kp] for kp in adjusted[:17]])
        return formatted

    # 保存对齐后的结果
    with open(output_path1, "w") as f:
        json.dump(format_output(aligned1), f)
    with open(output_path2, "w") as f:
        json.dump(format_output(aligned2), f)


def calculate_similarity_and_low_similarity_frames(
    json_path1, json_path2, resolution, weights, max_distance_threshold=1250
):
    """
    计算两个关键点序列之间的相似度，并标记低相似度帧。

    参数：
        json_path1 (str): 第一个关键点 JSON 文件路径。
        json_path2 (str): 第二个关键点 JSON 文件路径。
        resolution (tuple): 视频分辨率 (宽度, 高度)。
        weights (list): 每个关键点的权重，长度为17。
        max_distance_threshold (float): 标记低相似度帧的加权距离阈值，默认1250。

    返回：
        list: 每帧的相似度百分比。
        list: 低相似度帧的索引。
    """
    # 加载两个 JSON 文件
    with open(json_path1, "r") as f1:
        keypoints1 = json.load(f1)
    with open(json_path2, "r") as f2:
        keypoints2 = json.load(f2)

    # 检查帧数是否一致
    if len(keypoints1) != len(keypoints2):
        raise ValueError("两个关键点序列的帧数不一致")

    # 计算视频分辨率的最大可能距离（对角线）
    max_distance = np.sqrt(resolution[0] ** 2 + resolution[1] ** 2)

    similarity_scores = []
    low_similarity_frames = []

    # 遍历每帧关键点
    for frame_idx, (frame1, frame2) in enumerate(zip(keypoints1, keypoints2)):
        # 跳过包含 NaN 值的帧
        if any(np.isnan(kp).any() for kp in frame1) or any(
            np.isnan(kp).any() for kp in frame2
        ):
            similarity_scores.append(0)
            low_similarity_frames.append(frame_idx)
            continue

        # 计算两帧之间的加权欧氏距离
        distances = [
            weights[i] * np.linalg.norm(np.array(kp1) - np.array(kp2))
            for i, (kp1, kp2) in enumerate(zip(frame1, frame2))
        ]
        total_distance = sum(distances)

        # 转换为相似度百分比
        similarity = max(0, (1 - total_distance / (max_distance * sum(weights))) * 100)
        similarity_scores.append(similarity)

        # 检测低相似度帧
        if total_distance > max_distance_threshold:
            low_similarity_frames.append(frame_idx)

    return similarity_scores, low_similarity_frames


def generate_overlay_video(
    video1_path,
    video2_path,
    similarity_scores,
    output_path,
):
    """
    生成叠加显示视频，带进度条。

    参数：
        video1_path (str): 第一个处理后的视频路径。
        video2_path (str): 第二个处理后的视频路径。
        similarity_scores (list): 每帧相似度百分比。
        output_path (str): 输出叠加视频路径。
    """

    # 打开视频
    cap1 = cv2.VideoCapture(video1_path)
    cap2 = cv2.VideoCapture(video2_path)

    if not cap1.isOpened() or not cap2.isOpened():
        raise ValueError("无法打开视频")

    # 获取视频参数
    fps = cap1.get(cv2.CAP_PROP_FPS)
    width = int(cap1.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap1.get(cv2.CAP_PROP_FRAME_HEIGHT))
    size = (width, height)

    # 获取视频总帧数
    total_frames = int(cap1.get(cv2.CAP_PROP_FRAME_COUNT))

    # 初始化输出视频
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(output_path, fourcc, fps, size)

    # 初始化进度条
    progress_bar = tqdm(total=total_frames, desc="Processing frames", unit="frame")

    frame_idx = 0

    while True:
        ret1, frame1 = cap1.read()
        ret2, frame2 = cap2.read()

        if not ret1 or not ret2:
            break

        # 调整第二个视频的分辨率与第一个一致
        frame2 = cv2.resize(frame2, (width, height))

        # 帧融合
        overlay_frame = cv2.addWeighted(frame1, 0.5, frame2, 0.5, 0)

        # 添加相似度标注
        similarity = similarity_scores[frame_idx]
        if similarity >= 90:
            color = (0, 255, 0)  # 绿色
        elif similarity >= 75:
            color = (0, 255, 255)  # 黄色
        else:
            color = (0, 0, 255)  # 红色

        text = f"Similarity: {similarity:.2f}%"
        cv2.putText(
            overlay_frame,
            text,
            (width - 300, 50),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            color,
            2,
        )

        # 写入输出视频
        out.write(overlay_frame)

        # 更新进度条
        progress_bar.update(1)

        frame_idx += 1

    cap1.release()
    cap2.release()
    out.release()

def process_single_frame(
    frame: np.ndarray,
    standard_kp_json: list,
    model: YOLO,
    frame_index: int,
    weights: list,
    resolution: tuple,
    skeleton_conn: list = [
        (0, 1), (0, 2), (1, 3), (2, 4),       # 头部
        (5, 6), (5, 7), (7, 9), (6, 8),      # 躯干和手臂
        (8, 10), (11, 12), (5, 11), (6, 12), # 髋部连接
        (11, 13), (13, 15), (12, 14), (14, 16) # 腿部
    ]
) -> np.ndarray:
    """
    修改版：仅显示用户骨骼（绿色），不显示标准参考骨骼
    """
    # 获取标准关键点（仅用于计算，不显示）
    standard_norm_kp = np.array(standard_kp_json[frame_index % len(standard_kp_json)]).astype(float)
    
    # 姿态估计
    results = model(frame, verbose=False)[0]
    vis_frame = frame.copy()
    
    if results.keypoints is None or len(results.keypoints.xy) == 0:
        cv2.putText(vis_frame, "No pose detected", (50, 50), 
                   cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
        return vis_frame

    # 当前帧关键点
    current_abs_kp = results.keypoints.xy[0].cpu().numpy()
    mid_shoulder = (current_abs_kp[5] + current_abs_kp[6]) / 2
    
    # ========= 关键修改：移除标准骨骼绘制 =========
    # 仅保留相似度计算所需的标准关键点处理（不显示）
    current_norm_kp = current_abs_kp - mid_shoulder
    total_distance = 0.0
    valid = True
    
    for i in range(17):
        if np.isnan(current_norm_kp[i]).any() or np.isnan(standard_norm_kp[i]).any():
            valid = False
            break
        distance = np.linalg.norm(current_norm_kp[i] - standard_norm_kp[i])
        total_distance += weights[i] * distance

    # 相似度计算
    max_distance = np.sqrt(resolution[0]**2 + resolution[1]**2)
    if valid:
        similarity = max(0.0, min(100.0, (1 - total_distance/(max_distance*sum(weights)))*100))
        color = (0, 255, 0)  # 仅用绿色显示
    else:
        similarity = 0.0
        color = (0, 0, 255)
    
    # ========= 仅绘制用户骨骼 =========
    # 绘制关键点
    for idx, (x, y) in enumerate(current_abs_kp):
        cv2.circle(vis_frame, (int(x), int(y)), 5, (0, 255, 0), -1)
    
    # 修改骨骼连接绘制逻辑，跳过无效关键点
    # 绘制骨骼连接的修改部分
    for (start, end) in skeleton_conn:
        # 1. 检查索引是否越界
        if start >= len(current_abs_kp) or end >= len(current_abs_kp):
            continue
        
        # 2. 获取坐标并检查有效性（非NaN、非零点、在图像范围内）
        kp_start = current_abs_kp[start]
        kp_end = current_abs_kp[end]
        
        # 定义无效坐标条件
        is_invalid_start = np.isnan(kp_start).any() or np.allclose(kp_start, [0, 0], atol=1e-3)
        is_invalid_end = np.isnan(kp_end).any() or np.allclose(kp_end, [0, 0], atol=1e-3)
        
        if is_invalid_start or is_invalid_end:
            continue
        
        # 3. 转换为整数坐标并检查边界
        x1, y1 = int(kp_start[0]), int(kp_start[1])
        x2, y2 = int(kp_end[0]), int(kp_end[1])
        
        if (0 <= x1 < resolution[0] and 0 <= y1 < resolution[1] and
            0 <= x2 < resolution[0] and 0 <= y2 < resolution[1]):
            cv2.line(vis_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
        
        x1, y1 = map(int, current_abs_kp[start])
        x2, y2 = map(int, current_abs_kp[end])
        cv2.line(vis_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
    
    # 显示相似度
    text = f"Similarity: {similarity:.1f}%" if valid else "Invalid Pose"
    text_size = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 1, 2)[0]
    text_x = vis_frame.shape[1] - text_size[0] - 20
    text_y = 50
    cv2.rectangle(vis_frame, 
                (text_x - 10, text_y - text_size[1] - 10), 
                (text_x + text_size[0] + 10, text_y + 10), 
                (0,0,0), -1)
    cv2.putText(vis_frame, text, (text_x, text_y),
        cv2.FONT_HERSHEY_DUPLEX, 1, (0,255,0), 2, cv2.LINE_AA)
    
    return vis_frame

if __name__ == "__main__":
    # 原始的处理流程
    process_pose_videos(
        video1_path=r"movies/1.mp4",
        video2_path=r"movies/2.mp4",
        output_vid1_path=r"movies/process_1.mp4",
        output_vid2_path=r"movies/process_2.mp4",
        keypoints1_path=r"keypoints/kp1.json",
        keypoints2_path=r"keypoints/kp2.json",
    )
    align_keypoints(
        r"keypoints/kp1.json",
        r"keypoints/kp2.json",
        r"keypoints/aligned1.json",
        r"keypoints/aligned2.json",
    )
    
    # 相似度计算和视频生成
    json_path1 = r"keypoints/aligned1.json"
    json_path2 = r"keypoints/aligned2.json"
    resolution = (640, 360)
    weights = [0.2, 0.5, 0.5, 0.7, 0.7, 0.6, 0.6, 0.7, 0.7, 0.6, 0.6, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]

    similarity_scores, low_similarity_frames = calculate_similarity_and_low_similarity_frames(
        json_path1, json_path2, resolution, weights
    )
    generate_overlay_video(
        video1_path=r"movies/process_1.mp4",
        video2_path=r"movies/process_2.mp4",
        similarity_scores=similarity_scores,
        output_path=r"movies/Overlay.mp4",
    )

    # 新增的摄像头测试代码
    print("\n启动实时姿态对比测试（按 Q 退出）...")
    
    # 加载标准关键点
    with open(r"keypoints/aligned1.json", "r") as f:
        standard_kp = json.load(f)
    
    # 初始化模型
    model = YOLO(r"models\yolo11n-pose.pt")
    
    # 打开摄像头
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, resolution[0])
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, resolution[1])
    
    frame_index = 0
    try:
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                print("无法获取视频帧")
                break

            # 处理当前帧
            processed_frame = process_single_frame(
                frame=frame,
                standard_kp_json=standard_kp,
                model=model,
                frame_index=frame_index,
                weights=weights,
                resolution=resolution
            )
            
            # 显示处理结果
            cv2.imshow('Real-time Pose Comparison', processed_frame)
            frame_index += 1
            
            # 退出机制
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()  
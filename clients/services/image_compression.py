"""Image compression utilities for document uploads."""
from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path
from typing import BinaryIO

from django.conf import settings
from django.core.files.uploadedfile import InMemoryUploadedFile
from PIL import Image

logger = logging.getLogger(__name__)

# Default settings
DEFAULT_QUALITY = 85
DEFAULT_MAX_WIDTH = 2000
DEFAULT_MAX_HEIGHT = 2000
SUPPORTED_FORMATS = {'.jpg', '.jpeg', '.png', '.tiff', '.tif', '.bmp'}


def get_compression_settings() -> dict:
    """Get compression settings from Django settings."""
    return {
        'quality': getattr(settings, 'IMAGE_COMPRESSION_QUALITY', DEFAULT_QUALITY),
        'max_width': getattr(settings, 'IMAGE_MAX_WIDTH', DEFAULT_MAX_WIDTH),
        'max_height': getattr(settings, 'IMAGE_MAX_HEIGHT', DEFAULT_MAX_HEIGHT),
        'convert_to_webp': getattr(settings, 'IMAGE_CONVERT_TO_WEBP', True),
    }


def should_compress(file_path: str | Path) -> bool:
    """Check if file should be compressed based on extension."""
    suffix = Path(file_path).suffix.lower()
    return suffix in SUPPORTED_FORMATS


def compress_image(
    image_file: BinaryIO | InMemoryUploadedFile,
    output_format: str = 'WEBP',
    quality: int | None = None,
    max_width: int | None = None,
    max_height: int | None = None,
) -> tuple[BytesIO, str]:
    """
    Compress image and return BytesIO buffer with compressed data.
    
    Args:
        image_file: Input image file or file-like object
        output_format: Output format ('WEBP', 'JPEG', 'PNG')
        quality: Compression quality (1-100)
        max_width: Maximum width in pixels
        max_height: Maximum height in pixels
        
    Returns:
        Tuple of (compressed_buffer, new_extension)
    """
    # Get settings
    settings_dict = get_compression_settings()
    quality = quality or settings_dict['quality']
    max_width = max_width or settings_dict['max_width']
    max_height = max_height or settings_dict['max_height']
    
    # Open image
    try:
        img = Image.open(image_file)
        
        # Convert RGBA to RGB if needed (for JPEG/WEBP)
        if img.mode in ('RGBA', 'LA', 'P') and output_format in ('JPEG', 'WEBP'):
            # Create white background
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
            img = background
        
        # Resize if too large
        original_size = img.size
        if img.width > max_width or img.height > max_height:
            img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)
            logger.info(f"Resized image from {original_size} to {img.size}")
        
        # Compress to buffer
        buffer = BytesIO()
        save_kwargs = {'format': output_format, 'optimize': True}
        
        if output_format in ('JPEG', 'WEBP'):
            save_kwargs['quality'] = quality
        
        img.save(buffer, **save_kwargs)
        buffer.seek(0)
        
        # Determine new extension
        extension_map = {
            'WEBP': '.webp',
            'JPEG': '.jpg',
            'PNG': '.png',
        }
        new_ext = extension_map.get(output_format, '.webp')
        
        # Log compression stats
        original_size_kb = image_file.size / 1024 if hasattr(image_file, 'size') else 0
        compressed_size_kb = len(buffer.getvalue()) / 1024
        if original_size_kb > 0:
            savings = ((original_size_kb - compressed_size_kb) / original_size_kb) * 100
            logger.info(
                f"Compressed image: {original_size_kb:.1f}KB → {compressed_size_kb:.1f}KB "
                f"(saved {savings:.1f}%)"
            )
        
        return buffer, new_ext
        
    except Exception as e:
        logger.exception(f"Failed to compress image: {e}")
        raise


def compress_uploaded_file(uploaded_file: InMemoryUploadedFile) -> InMemoryUploadedFile | None:
    """
    Compress an uploaded Django file and return new InMemoryUploadedFile.
    
    Args:
        uploaded_file: Django uploaded file
        
    Returns:
        New compressed InMemoryUploadedFile or None if compression failed
    """
    if not should_compress(uploaded_file.name):
        return None
    
    try:
        settings_dict = get_compression_settings()
        output_format = 'WEBP' if settings_dict['convert_to_webp'] else 'JPEG'
        
        buffer, new_ext = compress_image(
            uploaded_file,
            output_format=output_format,
            quality=settings_dict['quality'],
            max_width=settings_dict['max_width'],
            max_height=settings_dict['max_height'],
        )
        
        # Change file extension
        original_path = Path(uploaded_file.name)
        new_name = str(original_path.with_suffix(new_ext))
        
        # Create new InMemoryUploadedFile
        compressed_file = InMemoryUploadedFile(
            file=buffer,
            field_name=uploaded_file.field_name,
            name=new_name,
            content_type=f'image/{output_format.lower()}',
            size=len(buffer.getvalue()),
            charset=uploaded_file.charset,
        )
        
        return compressed_file
        
    except Exception as e:
        logger.warning(f"Could not compress file {uploaded_file.name}: {e}")
        return None


def compress_existing_file(file_path: str | Path) -> bool:
    """
    Compress an existing file on disk and replace it.
    
    Args:
        file_path: Path to existing file
        
    Returns:
        True if compressed successfully, False otherwise
    """
    file_path = Path(file_path)
    
    if not file_path.exists() or not should_compress(file_path):
        return False
    
    try:
        with file_path.open('rb') as f:
            settings_dict = get_compression_settings()
            output_format = 'WEBP' if settings_dict['convert_to_webp'] else 'JPEG'
            
            buffer, new_ext = compress_image(
                f,
                output_format=output_format,
            )
        
        # Write compressed file
        new_path = file_path.with_suffix(new_ext)
        with new_path.open('wb') as f:
            f.write(buffer.getvalue())
        
        # Remove old file if extension changed
        if new_path != file_path:
            file_path.unlink()
        
        logger.info(f"Compressed existing file: {file_path} → {new_path}")
        return True
        
    except Exception as e:
        logger.exception(f"Failed to compress existing file {file_path}: {e}")
        return False

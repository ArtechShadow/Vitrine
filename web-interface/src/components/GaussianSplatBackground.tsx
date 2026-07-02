import { useEffect, useRef } from "react";

const VERTEX = `#version 300 es
in vec2 a_pos;
void main() {
  gl_Position = vec4(a_pos, 0.0, 1.0);
}
`;

const FRAGMENT = `#version 300 es
precision highp float;

uniform vec2 u_resolution;
uniform float u_time;
uniform float u_intensity;

out vec4 outColor;

float hash11(float p) {
  return fract(sin(p * 127.1) * 43758.5453123);
}

vec2 hash22(float p) {
  float x = hash11(p);
  float y = hash11(p + 19.19);
  return vec2(x, y);
}

vec3 splatColor(float id) {
  float t = hash11(id * 3.17);
  vec3 teal = vec3(0.18, 0.83, 0.75);
  vec3 cyan = vec3(0.36, 0.78, 0.92);
  vec3 accent = vec3(0.78, 0.12, 0.16);
  vec3 violet = vec3(0.52, 0.38, 0.92);
  vec3 pearl = vec3(0.86, 0.82, 0.95);
  vec3 c = mix(teal, cyan, smoothstep(0.15, 0.8, t));
  c = mix(c, violet, smoothstep(0.45, 0.95, hash11(id * 5.1)) * 0.55);
  c = mix(c, accent, smoothstep(0.82, 1.0, hash11(id * 7.3)) * 0.35);
  c = mix(c, pearl, smoothstep(0.78, 1.0, hash11(id * 11.7)) * 0.4);
  return c;
}

float gaussian(vec2 d, vec2 invSigma) {
  vec2 scaled = d * invSigma;
  return exp(-0.5 * dot(scaled, scaled));
}

void main() {
  vec2 uv = (gl_FragCoord.xy / u_resolution) * 2.0 - 1.0;
  uv.x *= u_resolution.x / u_resolution.y;

  vec3 accum = vec3(0.015, 0.015, 0.02);
  float bloom = 0.0;

  for (int i = 0; i < 96; i++) {
    float fi = float(i);
    vec2 seed = hash22(fi + 0.5);

    float layer = hash11(fi * 1.91);
    float depth = 0.35 + layer * 0.65;
    float orbitSpeed = 0.05 + layer * 0.11;
    float orbitRadius = 0.18 + seed.x * 0.72;
    float phase = fi * 1.37 + seed.y * 6.28318;

    float angle = u_time * orbitSpeed + phase;
    vec2 center = vec2(cos(angle), sin(angle * 0.93 + 0.4)) * orbitRadius;
    center += vec2(
      sin(u_time * (0.18 + layer * 0.2) + fi * 0.31),
      cos(u_time * (0.14 + layer * 0.16) + fi * 0.47)
    ) * (0.06 + layer * 0.08);

    vec2 delta = uv - center;
    float stretch = 0.65 + hash11(fi * 2.7) * 1.1;
    float rotation = u_time * (0.12 + hash11(fi * 4.2) * 0.35) + fi;
    float c = cos(rotation);
    float s = sin(rotation);
    delta = vec2(c * delta.x - s * delta.y, s * delta.x + c * delta.y);
    delta.x *= stretch;

    float radius = (0.045 + hash11(fi * 5.9) * 0.11) / depth;
    vec2 invSigma = vec2(1.0 / radius, 1.0 / (radius * (0.75 + hash11(fi * 8.4) * 0.55)));

    float g = gaussian(delta, invSigma);
    vec3 col = splatColor(fi);
    float weight = g * (0.22 + layer * 0.38) / depth;

    accum += col * weight;
    bloom += g * weight * 0.35;
  }

  accum += vec3(0.18, 0.03, 0.05) * bloom * 0.55;
  accum = accum / (accum + vec3(0.85));

  float vignette = smoothstep(1.35, 0.15, length(uv * vec2(0.92, 1.0)));
  accum *= mix(0.42, 1.0, vignette);

  float grain = (hash11(dot(uv, vec2(12.7, 78.2)) + u_time * 0.01) - 0.5) * 0.018;
  accum += grain;

  outColor = vec4(accum * u_intensity, 1.0);
}
`;

function compileShader(gl: WebGL2RenderingContext, type: number, source: string) {
  const shader = gl.createShader(type);
  if (!shader) return null;
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    console.warn("Splat background shader:", gl.getShaderInfoLog(shader));
    gl.deleteShader(shader);
    return null;
  }
  return shader;
}

export default function GaussianSplatBackground() {
  const hostRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const host = hostRef.current;
    const canvas = canvasRef.current;
    if (!host || !canvas) return;

    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const gl = canvas.getContext("webgl2", { alpha: true, antialias: false });
    if (!gl) return;

    const vs = compileShader(gl, gl.VERTEX_SHADER, VERTEX);
    const fs = compileShader(gl, gl.FRAGMENT_SHADER, FRAGMENT);
    if (!vs || !fs) return;

    const program = gl.createProgram();
    if (!program) return;
    gl.attachShader(program, vs);
    gl.attachShader(program, fs);
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      console.warn("Splat background program:", gl.getProgramInfoLog(program));
      return;
    }

    const buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);

    const vao = gl.createVertexArray();
    gl.bindVertexArray(vao);
    const loc = gl.getAttribLocation(program, "a_pos");
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);

    const uResolution = gl.getUniformLocation(program, "u_resolution");
    const uTime = gl.getUniformLocation(program, "u_time");
    const uIntensity = gl.getUniformLocation(program, "u_intensity");

    let raf = 0;
    let start = performance.now();
    let width = 0;
    let height = 0;

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      width = Math.max(1, Math.floor(host.clientWidth * dpr));
      height = Math.max(1, Math.floor(host.clientHeight * dpr));
      if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width;
        canvas.height = height;
        gl.viewport(0, 0, width, height);
      }
    };

    const observer = new ResizeObserver(resize);
    observer.observe(host);
    resize();

    const draw = (now: number) => {
      const elapsed = (now - start) * 0.001;
      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.useProgram(program);
      gl.uniform2f(uResolution, width, height);
      gl.uniform1f(uTime, reducedMotion ? 0.0 : elapsed);
      gl.uniform1f(uIntensity, 1.0);
      gl.bindVertexArray(vao);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
      raf = requestAnimationFrame(draw);
    };

    raf = requestAnimationFrame(draw);

    return () => {
      cancelAnimationFrame(raf);
      observer.disconnect();
      gl.deleteProgram(program);
      gl.deleteShader(vs);
      gl.deleteShader(fs);
      gl.deleteBuffer(buffer);
      gl.deleteVertexArray(vao);
    };
  }, []);

  return (
    <div ref={hostRef} className="splat-background" aria-hidden>
      <canvas ref={canvasRef} />
      <div className="splat-background-veil" />
    </div>
  );
}